from django.db import models
from bookings.models import Booking
from decimal import Decimal

# Create your models here.
class Payment(models.Model):
    PAYMENT_STATUS = [
        ("pending", "Pendiente"),
        ("paid", "Pagado"),
        ("failed", "Fallido"),
        ("requires_action", "Requiere intervención")
    ]
    REFUND_STATUS = [
        ("none", "Nulo"),
        ("pending","Pendiente"),
        ("paid", "Pagado"),
        ("failed", "Fallido")
    ]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    stripe_payment_intent_id= models.CharField(max_length=255, null=True, blank=True, verbose_name="Id_Stripe")
    payment_type = models.CharField(max_length=20, choices=[
        ("deposit","Anticipo"),
        ("balance","Saldo"),
        ("cancellation_fee", "Penalización por cancelación"),
        ("no_show", "Penalización por no aparecer"),
        ], verbose_name="Tipo de pago")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, verbose_name="Estado", default="pending")
    amount = models.DecimalField(max_digits=10, verbose_name= "Cantidad", decimal_places=2)
    currency = models.CharField(max_length=10, verbose_name="Divisa", default= "MXN")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Id sesión de stripe")

    #REEMBOLSOS

    refund_status = models.CharField(max_length=20, choices=REFUND_STATUS, default="none", verbose_name="Estado del reembolso")
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Monto devuelto")
    stripe_refund_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Id del reembolso")
    refund_count = models.PositiveIntegerField(default=0, verbose_name="Número de reembolsos")
    last_refund_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de último reembolso")
    refund_reason = models.CharField(max_length=64, blank=True, null=True, verbose_name="Razón de reembolso")

    #Helpers

    def is_fully_refunded(self) -> bool : 
        return self.refunded_amount >= self.amount and self.refund_status == "paid"

    class Meta():
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"

    def __str__(self):
        return f"Pago de {self.booking.user.username} => {self.booking.property.name} - {self.status}"
    

class RefundLog(models.Model):
    stripe_refund_id = models.CharField(max_length=255, unique=True, verbose_name="Id del Reembolso")
    payment = models.ForeignKey("payments.Payment", verbose_name="Pago asociado", related_name="refund_logs", on_delete=models.CASCADE) # El string del principo es una forma más segura de referirse a otro modelo, para evitar importaciones circulares(muy usado en apps grandes)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Monto reembolsado")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    class Meta:
        verbose_name = "Registro de reembolso"
        verbose_name_plural = "Registro de reembolsos"
        indexes=[
            models.Index(fields=["payment"]),
        ]

    def __str__(self):
        return f"Pago con id: {self.stripe_refund_id} · {self.amount}"