import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta
from payments.tasks import charge_balance_for_booking, scan_and_charge_balances
from payments.models import Payment

@pytest.mark.django_db
def test_charge_balance_succeeded(monkeypatch):
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("700.00"),
        total_amount=Decimal("1000.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
    )

    # no topups, no paid balance
    assert not Payment.objects.filter(booking=b, payment_type="balance").exists()

    # mock stripe → off-session OK
    def fake_create_pi(**kwargs):
        class PI: id = "pi_ok"; status = "succeeded"
        return PI()
    monkeypatch.setattr("payments.services.stripe.PaymentIntent.create", fake_create_pi)

    # que no intente crear checkout
    def fake_session_create(**kwargs): raise AssertionError("No debe crear Checkout")
    monkeypatch.setattr("payments.services.stripe.checkout.Session.create", fake_session_create)

    res = charge_balance_for_booking.delay(b.id, "http://127.0.0.1:8000").get()
    assert res == "succeeded"

    p = Payment.objects.get(booking=b, payment_type="balance")
    assert p.status == "paid"
    assert p.stripe_payment_intent_id == "pi_ok"

@pytest.mark.django_db
def test_charge_balance_requires_action_crea_checkout(monkeypatch):
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("700.00"),
        total_amount=Decimal("1000.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
    )

    # simula CardError → requires_action
    class DummyStripeError(Exception): pass
    class DummyStripeCardError(Exception):
        def __init__(self):
            class Err: 
                payment_intent = {"id": "pi_need_3ds"}
            self.error = Err()

    # Stripe eleva CardError
    import stripe
    class FakeErr:
        payment_intent = {"id": "pi_need_3ds"}
    class FakeCardError(stripe.error.CardError):
        def __init__(self): pass  # no llamamos a super para no liar args
        @property
        def error(self): return FakeErr()

    def fake_create_pi(**kwargs):
        raise FakeCardError()

    monkeypatch.setattr("payments.services.stripe.PaymentIntent.create", fake_create_pi)


    # y crea Checkout Session
    class SessionObj:
        id = "cs_123"
        url = "https://stripe.test/checkout/cs_123"
    monkeypatch.setattr("payments.services.stripe.checkout.Session.create", lambda **k: SessionObj())

    res = charge_balance_for_booking.delay(b.id, "http://127.0.0.1:8000").get()
    assert res == "requires_action"

    p = Payment.objects.get(booking=b, payment_type="balance")
    assert p.status == "requires_action"
    assert p.stripe_checkout_session_id == "cs_123"
    assert p.stripe_payment_intent_id == "pi_need_3ds"

@pytest.mark.django_db
def test_charge_balance_missing_method():
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("700.00"),
        total_amount=Decimal("1000.00"),
        stripe_customer_id=None,
        stripe_payment_method_id=None,
    )
    res = charge_balance_for_booking.delay(b.id, "http://127.0.0.1:8000").get()
    assert res == "missing_method"

@pytest.mark.django_db
def test_charge_balance_pending_topup_bloquea():
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("700.00"),
        total_amount=Decimal("1000.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
    )
    baker.make(
        "payments.Payment",
        booking=b,
        payment_type="deposit",
        status="pending",
        amount=Decimal("50.00"),
        metadata={"payment_role":"deposit_topup"},
    )
    res = charge_balance_for_booking.delay(b.id, "http://127.0.0.1:8000").get()
    assert res == "pending_topup"

@pytest.mark.django_db
def test_charge_balance_already_paid_no_duplicar():
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("0.00"),  # balance ya liquidado
        total_amount=Decimal("1000.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
    )
    baker.make("payments.Payment", booking=b, payment_type="balance", status="paid", amount=Decimal("700.00"))
    res = charge_balance_for_booking.delay(b.id, "http://127.0.0.1:8000").get()
    # tu task devuelve "no_balance" si amount <= 0; si cambias, ajusta aserción
    assert res in ("already_paid", "no_balance")

@pytest.mark.django_db
def test_scan_and_charge_balances_enqueja_solo_mayores_48h(monkeypatch):
    # una candidata (≥48h)
    old = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(days=3),
        balance_due=Decimal("100.00"),
        total_amount=Decimal("500.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
    )
    # no candidata (<48h)
    recent = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now() - timedelta(hours=30),
        balance_due=Decimal("100.00"),
        total_amount=Decimal("500.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
    )

    from types import SimpleNamespace

    calls = []

    class StubTask:
        def __call__(self, *a, **k):     # por si alguien la llama como función
            calls.append(("call", a))
        def delay(self, *a, **k):        # si usan .delay
            calls.append(("delay", a))
        def apply_async(self, args, **k):# si usan .apply_async
            calls.append(("apply_async", args))

    monkeypatch.setattr("payments.tasks.charge_balance_for_booking", StubTask(), raising=False)

    msg = scan_and_charge_balances.delay("http://127.0.0.1:8000").get()
    assert len(calls) == 1
    # según qué via se use, el tuple es ("delay", args) o ("apply_async", args)
    assert calls[0][1][0] == old.id if calls[0][0] != "call" else calls[0][0]  # o, más simple:
    kind, args = calls[0]
    assert (args[0] if kind != "apply_async" else args[0]) == old.id

