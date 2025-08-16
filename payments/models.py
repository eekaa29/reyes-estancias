from django.db import models
from bookings.models import Booking

# Create your models here.
class Payment(models.Model):
    PAYMENT_STATUS = [
        ("pending", "Pendiente"),
        ("paid", "Pagado"),
        ("failed", "Fallido"),
        ("requires_action", "Requiere intervención")
    ]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    stripe_payment_intent_id= models.CharField(max_length=255, null=True, blank=True, verbose_name="Id_Stripe")
    payment_type = models.CharField(max_length=20, choices=[
        ("deposit","Anticipo"),
        ("balance","Saldo"),
        ])
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, verbose_name="Estado", default="pending")
    amount = models.DecimalField(max_digits=10, verbose_name= "Cantidad", decimal_places=2)
    currency = models.CharField(max_length=10, verbose_name="Divisa", default= "MXN")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta():
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"

    def __str__(self):
        return f"Pago de {self.booking.user.username} => {self.booking.property.name} - {self.status}"