import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta

from bookings.services import apply_change_booking_dates
from bookings.models import BookingChangeLog
from payments.models import Payment


@pytest.mark.django_db
def test_extension_balance_pagado_cobra_unico_pago(monkeypatch, django_user_model):
    """
    Con el balance ya pagado, al extender la estancia debe cobrarse la diferencia
    en un único pago de tipo 'extension'. No debe crearse topup de depósito
    ni un nuevo pago de balance pendiente.

    Escenario:
        Reserva original: 3 noches, total=1000, depósito=300 (pagado), balance=700 (pagado)
        Extensión: 2 noches extra → T_new=1200 → extension_charge=200
    """
    today = timezone.now()

    prop = baker.make("properties.Property")
    booking = baker.make(
        "bookings.Booking",
        property=prop,
        status="confirmed",
        arrival=today + timedelta(days=20),
        departure=today + timedelta(days=23),
        total_amount=Decimal("1000.00"),
        deposit_amount=Decimal("300.00"),
        balance_due=Decimal("0.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid", amount=Decimal("300.00"))
    baker.make("payments.Payment", booking=booking, payment_type="balance",  status="paid", amount=Decimal("700.00"))

    ext_payment = baker.make(
        "payments.Payment",
        booking=booking,
        payment_type="extension",
        status="paid",
        amount=Decimal("200.00"),
    )

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("1200.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr(
        "bookings.services.charge_offsession_with_fallback",
        lambda *a, **kw: {"status": "paid", "payment": ext_payment},
    )

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=25)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert result["actions"]["extension_charge"] == Decimal("200.00")

    booking.refresh_from_db()
    assert booking.balance_due == Decimal("0.00")

    clog = BookingChangeLog.objects.get(booking=booking)
    assert clog.status == "applied"
    assert clog.new_balance_due == Decimal("200.00")

    # No debe haber topup de depósito ni balance pendiente creados
    assert not Payment.objects.filter(booking=booking, payment_type="deposit", status="pending").exists()
    assert not Payment.objects.filter(booking=booking, payment_type="balance",  status__in=["pending", "requires_action"]).exists()
