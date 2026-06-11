import pytest
from decimal import Decimal
from model_bakery import baker
from django.utils import timezone
from datetime import timedelta

from payments.services import compute_refund_plan


@pytest.mark.django_db
def test_fraude_cambio_fechas_usa_old_arrival():
    """El usuario mueve el check-in al futuro y cancela; debe aplicarse la política original."""
    today = timezone.now()

    booking = baker.make(
        "bookings.Booking",
        arrival=today + timedelta(days=10),
        departure=today + timedelta(days=14),
        total_amount=Decimal("1000.00"),
        status="confirmed",
    )
    baker.make(
        "bookings.BookingChangeLog",
        booking=booking,
        status="applied",
        created_at=today - timedelta(days=1),
        old_arrival=today + timedelta(days=3),
        new_arrival=today + timedelta(days=10),
        old_departure=today + timedelta(days=7),
        new_departure=today + timedelta(days=14),
        old_T=Decimal("700.00"),
        new_T=Decimal("1000.00"),
    )

    plan = compute_refund_plan(booking)

    assert plan["window"] == "lte7", "Debe detectar el fraude y usar la fecha original"


@pytest.mark.django_db
def test_reagenda_legitimo_mas_de_7_dias_usa_nueva_arrival():
    """
    Hace 8 dias       Usuario cambia las fechas de su reserva
                    old_arrival = today + 3 dias  (check-in que tenia antes)
                    new_arrival = today + 10 dias  (check-in nuevo)
                    BookingChangeLog.created_at = today - 8 dias

Hoy               Usuario cancela
                    booking.arrival = today + 10 dias  (el check-in actual, ya modificado)
                    compute_refund_plan busca cambios en los iºltimos 7 dias
                    el cambio fue hace 8 dias  no entra en el filtro
                    usa booking.arrival (10 dias)  gt7  reembolso del 100%

Es decir: el usuario cambió su check-in hace 8 dias, y hoy cancela. Como el cambio fue legítimamente hace mi¡s de 7 dias, el sistema respeta la fecha actual y le devuelve el 100%. No sabemos ni importa cui¡ndo hizo la reserva originalmente.
    El usuario reagendó hace >7 días; el cambio antiguo no debe penalizarle.
    
    """
    today = timezone.now()

    booking = baker.make(
        "bookings.Booking",
        arrival=today + timedelta(days=10),
        departure=today + timedelta(days=14),
        total_amount=Decimal("1000.00"),
        status="confirmed",
    )
    baker.make(
        "bookings.BookingChangeLog",
        booking=booking,
        status="applied",
        created_at=today - timedelta(days=8),
        old_arrival=today + timedelta(days=3),
        new_arrival=today + timedelta(days=10),
        old_departure=today + timedelta(days=7),
        new_departure=today + timedelta(days=14),
        old_T=Decimal("700.00"),
        new_T=Decimal("1000.00"),
    )

    plan = compute_refund_plan(booking)

    assert plan["window"] == "gt7", "Cambio legítimo antiguo no debe afectar al reembolso"
