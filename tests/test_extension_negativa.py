"""
Tests para extensiones negativas (reducción de estancia).

Caso B — balance NO pagado:
    T_new < T_old, paid_dep > T_new → reembolso del exceso de depósito.

Caso C2 — balance YA pagado:
    T_new < T_old → reembolso de (T_old - T_new) desde pagos extension/balance/deposit.
"""

import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta

from bookings.services import apply_change_booking_dates, quote_change_booking_dates
from bookings.models import BookingChangeLog
from payments.models import Payment


# ---------------------------------------------------------------------------
# Caso B — extensión negativa, balance no pagado
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_caso_b_reduccion_con_deposito_excedido_reembolsa(monkeypatch, django_user_model):
    """
    El cliente redujo la estancia antes de pagar el balance.
    El depósito pagado supera el nuevo total → se reembolsa el exceso.

    Escenario:
        T_old = 1000, deposit pagado = 300
        T_new = 200  (< paid_dep de 300)
        dep_refund = 300 - 200 = 100
        balance_next = 0
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
        balance_due=Decimal("700.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
        person_num=2,
    )
    deposit_payment = baker.make(
        "payments.Payment",
        booking=booking,
        payment_type="deposit",
        status="paid",
        amount=Decimal("300.00"),
        stripe_payment_intent_id="pi_dep",
    )
    baker.make(
        "payments.Payment",
        booking=booking,
        payment_type="balance",
        status="pending",
        amount=Decimal("700.00"),
    )

    refund_calls = []

    def fake_refund(payment, amount, reason="requested_by_customer"):
        refund_calls.append({"payment_id": payment.id, "amount": amount})
        return {"id": "re_fake"}

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("200.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr("payments.services.refund_payment", fake_refund)
    monkeypatch.setattr("bookings.services.reschedule_balance_charge", lambda *a, **kw: None)

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=21)  # 1 noche menos
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert result["actions"]["dep_refund"] == Decimal("100.00")

    booking.refresh_from_db()
    assert booking.total_amount == Decimal("200.00")
    assert booking.balance_due == Decimal("0.00")

    clog = BookingChangeLog.objects.get(booking=booking)
    assert clog.status == "applied"
    assert clog.deposit_refund == Decimal("100.00")

    # Se llamó a refund_payment con el importe correcto
    assert len(refund_calls) == 1
    assert refund_calls[0]["amount"] == Decimal("100.00")


@pytest.mark.django_db
def test_caso_b_reduccion_sin_deposito_excedido_solo_ajusta_balance(monkeypatch, django_user_model):
    """
    El cliente redujo la estancia pero el depósito no supera el nuevo total.
    No hay reembolso, solo se reduce el balance pendiente.

    Escenario:
        T_old = 1000, deposit pagado = 300
        T_new = 800  (> paid_dep de 300)
        dep_refund = 0
        balance_next = 800 - 300 = 500
    """
    today = timezone.now()
    prop = baker.make("properties.Property")
    booking = baker.make(
        "bookings.Booking",
        property=prop,
        status="confirmed",
        arrival=today + timedelta(days=20),
        departure=today + timedelta(days=25),
        total_amount=Decimal("1000.00"),
        deposit_amount=Decimal("300.00"),
        balance_due=Decimal("700.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid", amount=Decimal("300.00"))
    baker.make("payments.Payment", booking=booking, payment_type="balance", status="pending", amount=Decimal("700.00"))

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("800.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr("bookings.services.reschedule_balance_charge", lambda *a, **kw: None)

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=24)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert "dep_refund" not in result["actions"]

    booking.refresh_from_db()
    assert booking.total_amount == Decimal("800.00")
    assert booking.balance_due == Decimal("500.00")

    clog = BookingChangeLog.objects.get(booking=booking)
    assert clog.status == "applied"
    assert clog.deposit_refund == Decimal("0.00")
    assert clog.new_balance_due == Decimal("500.00")


@pytest.mark.django_db
def test_caso_b_quote_calcula_dep_refund_correctamente():
    """
    quote_change_booking_dates devuelve dep_refund cuando paid_dep > T_new
    y balance_next = 0.
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
        balance_due=Decimal("700.00"),
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid", amount=Decimal("300.00"))

    import unittest.mock as mock
    with mock.patch("bookings.services.compute_price", return_value=Decimal("200.00")), \
         mock.patch("properties.models.Property.is_available", return_value=True):
        q = quote_change_booking_dates(booking, today + timedelta(days=20), today + timedelta(days=21))

    assert q["ok"] is True
    assert q["dep_refund"] == Decimal("100.00")
    assert q["balance_next"] == Decimal("0.00")
    assert q["dep_topup"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Caso C2 — extensión negativa, balance YA pagado
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_caso_c2_reduccion_balance_pagado_reembolsa_desde_balance(monkeypatch, django_user_model):
    """
    Balance ya pagado. Se reduce la estancia.
    El reembolso debe venir primero del pago de balance (no del depósito).

    Escenario:
        T_old = 1000, deposit = 300 (paid), balance = 700 (paid)
        T_new = 800
        extension_refund = 1000 - 800 = 200  → se reembolsa del pago de balance
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
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid",
               amount=Decimal("300.00"), stripe_payment_intent_id="pi_dep")
    balance_payment = baker.make("payments.Payment", booking=booking, payment_type="balance", status="paid",
               amount=Decimal("700.00"), stripe_payment_intent_id="pi_bal")

    refund_calls = []

    def fake_refund(payment, amount, reason="requested_by_customer"):
        refund_calls.append({"payment_id": payment.id, "amount": amount})
        return {"id": "re_fake"}

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("800.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr("payments.services.refund_payment", fake_refund)

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=22)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert result["actions"]["extension_refund"] == Decimal("200.00")

    booking.refresh_from_db()
    assert booking.total_amount == Decimal("800.00")
    assert booking.balance_due == Decimal("0.00")
    assert booking.arrival == new_in
    assert booking.departure == new_out

    clog = BookingChangeLog.objects.get(booking=booking)
    assert clog.status == "applied"
    assert clog.new_T == Decimal("800.00")

    # El reembolso debe venir del pago de balance (no del depósito)
    assert len(refund_calls) == 1
    assert refund_calls[0]["payment_id"] == balance_payment.id
    assert refund_calls[0]["amount"] == Decimal("200.00")


@pytest.mark.django_db
def test_caso_c2_reduccion_balance_pagado_reembolsa_desde_extension_primero(monkeypatch, django_user_model):
    """
    Había un pago de extensión previo. El reembolso debe venir primero de extensión.

    Escenario:
        T_old = 1200 (= 1000 base + 200 extensión), deposit = 300 (paid),
        balance = 700 (paid), extension = 200 (paid)
        T_new = 1100
        extension_refund = 1200 - 1100 = 100 → se reembolsa del pago de extensión
    """
    today = timezone.now()
    prop = baker.make("properties.Property")
    booking = baker.make(
        "bookings.Booking",
        property=prop,
        status="confirmed",
        arrival=today + timedelta(days=20),
        departure=today + timedelta(days=25),
        total_amount=Decimal("1200.00"),
        deposit_amount=Decimal("360.00"),
        balance_due=Decimal("0.00"),
        stripe_customer_id="cus_test",
        stripe_payment_method_id="pm_test",
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid",
               amount=Decimal("300.00"), stripe_payment_intent_id="pi_dep")
    baker.make("payments.Payment", booking=booking, payment_type="balance", status="paid",
               amount=Decimal("700.00"), stripe_payment_intent_id="pi_bal")
    ext_payment = baker.make("payments.Payment", booking=booking, payment_type="extension", status="paid",
               amount=Decimal("200.00"), stripe_payment_intent_id="pi_ext")

    refund_calls = []

    def fake_refund(payment, amount, reason="requested_by_customer"):
        refund_calls.append({"payment_id": payment.id, "amount": amount})
        return {"id": "re_fake"}

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("1100.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)
    monkeypatch.setattr("payments.services.refund_payment", fake_refund)

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=20)
    new_out = today + timedelta(days=24)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert result["actions"]["extension_refund"] == Decimal("100.00")

    # El reembolso debe venir del pago de extensión
    assert len(refund_calls) == 1
    assert refund_calls[0]["payment_id"] == ext_payment.id
    assert refund_calls[0]["amount"] == Decimal("100.00")


@pytest.mark.django_db
def test_caso_c2_mismo_precio_no_genera_reembolso(monkeypatch, django_user_model):
    """
    El nuevo total es igual al antiguo (fechas distintas, mismo coste).
    No debe generarse ningún reembolso.
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
    baker.make("payments.Payment", booking=booking, payment_type="balance", status="paid", amount=Decimal("700.00"))

    monkeypatch.setattr("bookings.services.compute_price", lambda prop, ci, co: Decimal("1000.00"))
    monkeypatch.setattr("properties.models.Property.is_available", lambda self, *a, **kw: True)

    user = baker.make(django_user_model)
    new_in  = today + timedelta(days=21)
    new_out = today + timedelta(days=24)
    result = apply_change_booking_dates(booking, new_in, new_out, actor_user=user)

    assert result["ok"] is True
    assert "extension_refund" not in result["actions"]
    assert "extension_charge" not in result["actions"]

    booking.refresh_from_db()
    assert booking.balance_due == Decimal("0.00")


@pytest.mark.django_db
def test_caso_c2_quote_calcula_extension_refund_correctamente():
    """
    quote_change_booking_dates devuelve extension_refund cuando
    balance_already_paid y T_new < T_old.
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
        person_num=2,
    )
    baker.make("payments.Payment", booking=booking, payment_type="deposit", status="paid", amount=Decimal("300.00"))
    baker.make("payments.Payment", booking=booking, payment_type="balance", status="paid", amount=Decimal("700.00"))

    import unittest.mock as mock
    with mock.patch("bookings.services.compute_price", return_value=Decimal("800.00")), \
         mock.patch("properties.models.Property.is_available", return_value=True):
        q = quote_change_booking_dates(booking, today + timedelta(days=20), today + timedelta(days=22))

    assert q["ok"] is True
    assert q["balance_already_paid"] is True
    assert q["extension_refund"] == Decimal("200.00")
    assert q["extension_charge"] == Decimal("0.00")
