from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from decimal import Decimal
from bookings.models import Booking
from payments.services import charge_offsession_with_fallback

class Command(BaseCommand):
    help = "Prueba el cobro no-show de una booking"

    def add_arguments(self, parser):
        parser.add_argument("booking_id", type=int)

    def handle(self, *args, **opts):
        booking_id = opts["booking_id"]
        try:
            booking = Booking.objects.get(pk=booking_id)
        except Booking.DoesNotExist:
            raise CommandError("Booking no encontrada")

        already = booking.payments.filter(status="paid").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        fee = max(booking.total_amount - already, Decimal("0.00"))

        self.stdout.write(f"Total: {booking.total_amount} | Ya pagado: {already} | A cobrar (no-show): {fee}")

        res = charge_offsession_with_fallback(
            booking=booking,
            request=None,  # usa settings.PUBLIC_BASE_URL en el servicio
            amount=fee,
            payment_type="no_show",
            description=f"No show · {booking.property.name}",
        )
        self.stdout.write(str(res))
