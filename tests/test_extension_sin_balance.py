import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta

from bookings.services import apply_change_booking_dates
from bookings.models import BookingChangeLog
from payments.models import Payment

WEBHOOK_URL = "/payments/webhook/"


@pytest.mark.django_db
def test_extension_sin_balance_cobra_topup_y_no_toca_fechas(monkeypatch, django_user_model):
    """
    El cliente extiende la reserva sin haber pagado el balance todavía (Caso A).

    Escenario:
        Reserva original: 3 noches, total=1000, depósito=300 (pagado), balance=700 (pendiente)
        Extensión: 2 noches extra → T_new=1200
        deposit_target nuevo: 1200 * 0.30 = 360
        dep_topup: 360 - 300 = 60   ← segundo depósito a cobrar
        balance_next: 1200 - (300 + 60) = 840  ← balance actualizado

    Comportamiento esperado:
        - Se genera un checkout para el topup de 60
        - Las fechas y el total del booking NO se modifican hasta que se pague el topup
        - Se crea un BookingChangeLog en status='pending' con los importes correctos
        - No se crea ningún cobro off-session de balance
    """
    today = timezone.now()
    old_arrival   = today + timedelta(days=20)
    old_departure = today + timedelta(days=23)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=25)  # 2 noches extra

    prop = baker.make("properties.Property")
    booking = baker.make(
        "bookings.Booking",
        property=prop,
        status="confirmed",
        arrival=old_arrival,
        departure=old_departure,
        total_amount=Decimal("1000.00"),
        deposit_amount=Decimal("300.00"),
        balance_due=Decimal("700.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid", amount=Decimal("300.00"))
    # balance pendiente, aún no pagado
    baker.make("payments.Payment", booking=booking, payment_type="balance", status="pending", amount=Decimal("700.00"))

    # Pago de topup que devolverá el mock del checkout
    topup_payment = baker.make(
        "payments.Payment",
        booking=booking,
        payment_type="deposit",
        status="pending",
        amount=Decimal("60.00"),
        stripe_checkout_session_id="cs_topup_fake",
    )

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("1200.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr(
        "bookings.services.create_deposit_topup_checkout",
        lambda *a, **kw: {
            "status": "pending",
            "payment": topup_payment,
            "checkout_url": "https://checkout.stripe.com/fake",
        },
    )

    user = baker.make(django_user_model)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert result["actions"]["dep_topup"] == Decimal("60.00")
    assert result["actions"]["checkout_url"] == "https://checkout.stripe.com/fake"

    # Las fechas y el total NO deben haberse tocado
    booking.refresh_from_db()
    assert booking.arrival == old_arrival
    assert booking.departure == old_departure
    assert booking.total_amount == Decimal("1000.00")
    assert booking.balance_due == Decimal("700.00")

    # El log queda pendiente hasta que se pague el topup
    clog = BookingChangeLog.objects.get(booking=booking, status="pending")
    assert clog.deposit_topup == Decimal("60.00")
    assert clog.new_balance_due == Decimal("840.00")
    assert clog.new_T == Decimal("1200.00")

    # No debe haberse lanzado ningún cobro off-session de balance ni extensión
    assert not Payment.objects.filter(
        booking=booking,
        payment_type__in=["balance", "extension"],
        status="paid",
    ).exists()


@pytest.mark.django_db
def test_topup_pagado_aplica_fechas_y_recalcula_balance(monkeypatch, client):
    """
    Cuando el cliente paga el topup de depósito (webhook checkout.session.completed),
    el sistema debe:
    - Actualizar fechas y total del booking con los datos del clog
    - Recalcular balance_due → 840  (1200 - 300 depósito - 60 topup)
    - Marcar el clog como 'applied'
    - Marcar el topup payment como 'paid'

    El estado de partida replica lo que deja apply_change_booking_dates (Caso A):
    fechas sin tocar, clog en 'pending', topup pendiente de cobro.
    """
    today = timezone.now()
    old_arrival   = today + timedelta(days=20)
    old_departure = today + timedelta(days=23)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=25)

    prop = baker.make("properties.Property")
    booking = baker.make(
        "bookings.Booking",
        property=prop,
        status="confirmed",
        arrival=old_arrival,
        departure=old_departure,
        total_amount=Decimal("1000.00"),
        deposit_amount=Decimal("300.00"),
        balance_due=Decimal("700.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid",    amount=Decimal("300.00"))
    baker.make("payments.Payment", booking=booking, payment_type="balance",  status="pending", amount=Decimal("700.00"))

    clog = baker.make(
        "bookings.BookingChangeLog",
        booking=booking,
        status="pending",
        old_arrival=old_arrival,
        old_departure=old_departure,
        new_arrival=new_in,
        new_departure=new_out,
        old_T=Decimal("1000.00"),
        new_T=Decimal("1200.00"),
        paid_dep=Decimal("300.00"),
        deposit_topup=Decimal("60.00"),
        deposit_target=Decimal("360.00"),
        deposit_refund=Decimal("0.00"),
        old_balance=Decimal("700.00"),
        new_balance_due=Decimal("840.00"),
    )
    topup_payment = baker.make(
        "payments.Payment",
        booking=booking,
        payment_type="deposit",
        status="pending",
        amount=Decimal("60.00"),
        stripe_checkout_session_id="cs_topup_fake",
        metadata={"payment_role": "deposit_topup", "change_log_id": str(clog.id)},
    )

    fake_event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {
                "booking_id":    str(booking.id),
                "payment_id":    str(topup_payment.id),
                "change_log_id": str(clog.id),
            },
            "payment_intent": "pi_fake",
            "customer": "cus_test",
        }},
    }
    fake_pi = {"customer": "cus_test", "payment_method": {"id": "pm_test"}}

    monkeypatch.setattr("payments.views.stripe.Webhook.construct_event",  lambda payload, sig, secret: fake_event)
    monkeypatch.setattr("payments.views.stripe.PaymentIntent.retrieve",   lambda pi_id, **kw: fake_pi)
    monkeypatch.setattr("payments.views.reschedule_balance_charge",        lambda *a, **kw: None)

    response = client.post(WEBHOOK_URL, data=b"fake", content_type="application/json", HTTP_STRIPE_SIGNATURE="sig")
    assert response.status_code == 200

    booking.refresh_from_db()
    assert booking.arrival      == new_in
    assert booking.departure    == new_out
    assert booking.total_amount == Decimal("1200.00")
    assert booking.deposit_amount == Decimal("360.00")
    # compute_balance_due_snapshot: 1200 - 300(depósito) - 60(topup) = 840
    assert booking.balance_due  == Decimal("840.00")

    clog.refresh_from_db()
    assert clog.status == "applied"

    topup_payment.refresh_from_db()
    assert topup_payment.status == "paid"
