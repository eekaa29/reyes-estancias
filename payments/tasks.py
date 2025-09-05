from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from bookings.models import Booking
from payments.models import Payment
from .services import charge_offsession_with_fallback, compute_balance_due_snapshot
from django.db.models import Q
from decimal import Decimal



@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def charge_balance_for_booking(self, booking_id, base_str):

    """
    Cobra el balance de UNA reserva (idempotente).
    Reintenta si hay fallos transitorios.
    """

    booking = Booking.objects.select_related("property", "user").get(pk=booking_id)
    base = Decimal(base_str) if base_str is not None else None

    try:
        with transaction.atomic():
            b = booking.objects.select_for_update().get(pk=booking_id)
            if b.status != "confirmed":
                return "booking_not_confirmed"

            #info mínima
            if not (b.stripe_customer_id and b.stripe_payment_method_id):
                return "missing_method"

            # no cobres si no hace falta
            amount = compute_balance_due_snapshot(b)
            if amount <= 0:
                return "no_balance"

            # no cobres si hay top-up pendiente que bloquee

            if Payment.objects.filter(
                booking=b,
                payment_type="deposit",
                metadata__payment_role="deposit_topup",
                status__in=["pending", "requires_action"]).exists():
                return "pending_topup"

            # evita doble cargo si ya hay un balance pagado reciente

            if Payment.objects.filter(
                booking=b,
                payment_type="balance",
                status="paid").exists():
                return "already_paid"
        
        

        # fuera del select_for_update para no bloquear durante Stripe

        result = charge_offsession_with_fallback(
            booking=b, 
            request=None,
            amount=amount, 
            payment_type="balance", 
            description="Cargo del 70%", 
            base_url=base)
        status = result.get("status") if isinstance(result, dict) else result
        if status in ("paid", "already_paid"):
            return "succeeded"
        if status == "requires_action":
            return "requires_action"
        if status in ("no_balance", "skipped"):
            return "no_balance"
        if status == "missing_method":
            return "missing_method"
        return "failed"
    

    except Booking.DoesNotExist:
        return "not_found"
    except Exception as exc:
        # reintento básico (red/Stripe)
        raise self.retry(exc=exc)

@shared_task
def scan_and_charge_balances(base_url):

    """
    Encola cobros para reservas cuyo check-in fue hace ≥ 48h.
    Usa Celery Beat para llamar a esta task (p.ej., cada 15 min).
    """

    cutoff = timezone.now() - timedelta(days=2)

    qs = (Booking.objects.filter(
        status="confirmed",
        arrival__lte=cutoff,
        balance_due__gt=0,
        stripe_customer_id__isnull=False,
        stripe_payment_method_id__isnull=False,
    ).exclude(payments__payment_type="balance", payments__status="paid").distinct())

    enqueued = 0
    for b in qs.iterator(): #el iterator sirve para no cargar la qs entera en memoria, de esta manera los leemos en chunks(trozos) de 2000(valor default, pero se puede cambiar con chunk_size=lo que quieras)
        charge_balance_for_booking(b.id, base_url)
        enqueued += 1
    return f"enqueued={enqueued}"