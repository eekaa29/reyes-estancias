# payments/management/commands/test_refund.py
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.utils.timezone import now

from payments.models import Payment
from bookings.models import Booking
from payments.services import refund_payment  # tu función que llama Stripe. ¡Ojo a la ruta!

class Command(BaseCommand):
    help = "Prueba reembolsos de forma manual y segura (modo test de Stripe)."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--payment-id", type=int, help="ID del Payment a reembolsar (recomendado: depósito)")
        g.add_argument("--booking-id", type=int, help="Usa el último depósito pagado de esta booking")

        amt = parser.add_mutually_exclusive_group(required=True)
        amt.add_argument("--amount", type=str, help="Importe a reembolsar en MXN, p.ej. 100.00")
        amt.add_argument("--percent", type=str, help="Porcentaje del Payment a reembolsar, p.ej. 50 para 50%%")

        parser.add_argument("--overrefund", action="store_true",
                            help="Solicita más de lo disponible a propósito para verificar que se cape.")
        parser.add_argument("--dry-run", action="store_true",
                            help="No llama a Stripe, solo muestra cálculos.")
        parser.add_argument("--reason", type=str, default="requested_by_customer",
                            help="Motivo del refund en Stripe")

    def handle(self, *args, **opts):
        payment = self._resolve_payment(opts)
        if not payment:
            raise CommandError("No se encontró un Payment válido.")

        # Info base
        self.stdout.write(self.style.NOTICE(
            f"Payment #{payment.id} | type={payment.payment_type} | status={payment.status} "
            f"| amount={payment.amount} | refunded_amount={payment.refunded_amount or Decimal('0.00')} "
            f"| has_intent={'YES' if payment.stripe_payment_intent_id else 'NO'}"
        ))

        # Calcular amount solicitado
        amount_requested = self._parse_amount(opts, payment)

        # Simular over-refund si se pide
        if opts["overrefund"]:
            amount_requested = (payment.amount - (payment.refunded_amount or Decimal("0.00"))) + Decimal("10.00")
            self.stdout.write(self.style.WARNING(
                f"[overrefund] Solicitando {amount_requested} MXN (> remaining). "
                "Tu servicio debe capar a lo restante."
            ))

        # Mostrar remaining esperado (según BD actual)
        refunded_so_far = payment.refunded_amount or Decimal("0.00")
        remaining = max(payment.amount - refunded_so_far, Decimal("0.00"))
        self.stdout.write(f"Remaining (según BD): {remaining} MXN")

        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY-RUN] Pediría refund de {amount_requested} MXN (será capado a <= {remaining})"
            ))
            return

        # Ejecutar refund (tu función refund_payment ya hace: cap + None si no hay intent + convierte a centavos)
        refund = refund_payment(payment, amount_requested, reason=opts["reason"])
        if refund is None:
            self.stdout.write(self.style.WARNING("Refund no ejecutado (importe 0 / sin intent)."))
            return
        if isinstance(refund, dict) and refund.get("error"):
            self.stdout.write(self.style.ERROR(f"Stripe rechazó el refund: {refund}"))
            return


        # Éxito: mostrar datos del refund (Stripe)
        rid = getattr(refund, "id", None) or refund.get("id")
        ramt = getattr(refund, "amount", None) or refund.get("amount")
        rcur = getattr(refund, "currency", None) or refund.get("currency")
        rstatus = getattr(refund, "status", None) or refund.get("status")
        self.stdout.write(self.style.SUCCESS(
            f"Refund creado: id={rid} | amount={Decimal(ramt)/Decimal('100') if ramt is not None else 'N/A'} "
            f"{rcur or ''} | status={rstatus}"
        ))
        self.stdout.write(
            "Recuerda: el webhook ('refund.updated') actualizará refunded_amount/refund_status en tu BD."
        )

    # ------------------ helpers ------------------

    def _resolve_payment(self, opts):
        if opts["payment_id"]:
            try:
                return Payment.objects.get(pk=opts["payment_id"])
            except Payment.DoesNotExist:
                raise CommandError("Payment no existe.")
        else:
            # Buscar depósito pagado más reciente de la booking
            try:
                booking = Booking.objects.get(pk=opts["booking_id"])
            except Booking.DoesNotExist:
                raise CommandError("Booking no existe.")
            p = booking.payments.filter(payment_type="deposit", status="paid").order_by("-id").first()
            if not p:
                self.stdout.write(self.style.WARNING("La booking no tiene depósito pagado."))
            return p

    def _parse_amount(self, opts, payment):
        try:
            if opts["amount"] is not None:
                return Decimal(opts["amount"])
            # percent
            perc = Decimal(opts["percent"])
            if perc <= 0:
                raise CommandError("El porcentaje debe ser > 0.")
            base = payment.amount  # porcentaje sobre el pago original
            return (base * perc / Decimal("100")).quantize(Decimal("0.01"))
        except InvalidOperation:
            raise CommandError("Cantidad/porcentaje inválido.")
