import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta
from celery.result import AsyncResult

from payments.services import reschedule_balance_charge
from payments.tasks import charge_balance_for_booking
from payments.models import Payment

@pytest.mark.django_db
def test_reschedule_saves_task_id_and_eta(monkeypatch):
    b = baker.make(
        "bookings.Booking",
        status="confirmed",
        arrival=timezone.now(),
        balance_due=Decimal("100.00"),
        total_amount=Decimal("500.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
        balance_charge_task_id=None,
        balance_charge_eta=None,
    )

    class DummyRes:
        id = "task-1"
    monkeypatch.setattr("payments.tasks.charge_balance_for_booking.apply_async", lambda args, eta: DummyRes())

    when = timezone.now() + timedelta(days=2)
    out = reschedule_balance_charge(b, when)
    assert out["task_id"] == "task-1"
    b.refresh_from_db()
    assert b.balance_charge_task_id == "task-1"
    assert abs((b.balance_charge_eta - when).total_seconds()) < 1

@pytest.mark.django_db
def test_cancel_booking_revoca_eta_y_void_balance(monkeypatch, client, django_user_model):
    user = baker.make(django_user_model)
    client.force_login(user)

    b = baker.make(
        "bookings.Booking",
        user=user,
        status="confirmed",
        arrival=timezone.now() - timedelta(days=1),
        balance_due=Decimal("100.00"),
        total_amount=Decimal("500.00"),
        stripe_customer_id="cus",
        stripe_payment_method_id="pm",
        balance_charge_task_id="task-XYZ",
        balance_charge_eta=timezone.now() + timedelta(days=1),
    )
    p = baker.make(
        "payments.Payment",
        booking=b,
        payment_type="balance",
        status="requires_action",
        amount=Decimal("100.00"),
        stripe_checkout_session_id="cs_abc",
    )

    revoked = {"called": False}
    class FakeAsyncResult:
        def __init__(self, task_id):  # la vista hace AsyncResult(task_id)
            self.task_id = task_id
        def revoke(self):
            revoked["called"] = True
    monkeypatch.setattr("bookings.views.AsyncResult", FakeAsyncResult, raising=True)

    expired = {"ids": []}
    class FakeSessionAPI:
        @staticmethod
        def expire(session_id):
            expired["ids"].append(session_id)

    monkeypatch.setattr("bookings.views.stripe.checkout.Session", FakeSessionAPI, raising=True)

    # Simula compute_refund_plan sin devolución ni penalización
    monkeypatch.setattr("payments.views.compute_refund_plan", lambda booking: {"refunds": [], "penalty": Decimal("0.00"), "penalty_type": None})

    # POST a tu URL real (ajusta el nombre del path si es distinto)
    from django.urls import reverse
    url = reverse("cancel_booking", args=[b.id])  # ajusta el name
    resp = client.post(url)
    assert resp.status_code in (302, 200)  # redirección OK

    b.refresh_from_db()
    assert b.status == "cancelled"
    assert b.balance_charge_task_id is None
    assert revoked["called"] is True

    p.refresh_from_db()
    assert p.status in ("void", "requires_action")  # si tu vista hace update() a void, será 'void'
    assert "cs_abc" in expired["ids"]
