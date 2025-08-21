from django.db import models
from django.contrib.auth.models import User
from properties.models import Property
from decimal import Decimal

# Create your models here.

class Booking(models.Model):
    STATUS_CHOICES = [
    ("pending", "Pendiente"),
    ("confirmed", "Confirmado" ),
    ("cancelled", "Cancelado"),
    ("expired", "Expirada")
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="bookings")
    person_num = models.IntegerField(verbose_name="Cant.Personas")
    arrival = models.DateTimeField(verbose_name="LLegada")
    departure = models.DateTimeField(verbose_name="Salida")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Monto total")
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Total Depósito")
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Total Balance")
    status = models.CharField(max_length=20,choices=STATUS_CHOICES, default="pending", verbose_name="Estado")
    hold_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Expira")

    #Campos necesarios para el segundo cobro
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Id cliente stripe")
    stripe_payment_method_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Método de pago")
    
    
    def deposit_payment(self):
        return self.payments.filter(payment_type="deposit").order_by("-id").first()

    def deposit_paid(self):
        p = self.deposit_payment()
        return bool(p and p.status == "paid")
    
    
    def balance_payment(self):
        return self.payments.filter(payment_type="balance").order_by("-id").first()
    
    def balance_paid(self):
        p = self.balance_payment()
        return bool(p and p.status == "paid")


    class Meta():
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def __str__(self):
        return f"{self.property.name} - {self.user.username} - ({self.arrival} => {self.departure})"