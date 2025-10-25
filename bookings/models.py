from django.db import models
from django.contrib.auth.models import User
from properties.models import Property
from decimal import Decimal
from django.db.models import Sum
from reyes_estancias import settings

# Create your models here.

class Booking(models.Model):
    STATUS_CHOICES = [
    ("pending", "Pendiente"),
    ("confirmed", "Confirmado" ),
    ("cancelled", "Cancelado"),
    ("expired", "Expirada")
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Usuario")
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
    
    #ETA PARA COBRO OFF-SESSION CON CELERY 
    balance_charge_task_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Identificador de la tarea")
    balance_charge_eta = models.DateTimeField(null=True, blank=True, verbose_name="Fecha para cobro automático de balance")
    
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
    
    def dep_before_chage_dates(self):
        return self.payments.filter(payment_type="deposit", status="paid").aggregate(s=Sum("amount")) ["s"] or Decimal("0.00")
    
    def net_deposit_paid(self):
        paid_dep = self.payments.filter(payment_type="deposit", status="paid").aggregate(s=Sum("amount")) ["s"] or Decimal("0.00")
        refunded = self.payments.filter(payment_type="deposit", status="paid").aggregate(s=Sum("refunded_amount")) ["s"] or Decimal("0.00")
        return (paid_dep - refunded)
    
    def balance_due_runtime(self):
        balance_due = self.total_amount - self.net_deposit_paid()
        return balance_due if balance_due > 0 else Decimal("0.00")


    class Meta():
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def __str__(self):
        return f"{self.property.name} - {self.user.username} - ({self.arrival} => {self.departure})"
    

class BookingChangeLog(models.Model):
    LOG_STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("applied", "Aplicado"),
        ("superseded", "Reemplazado"),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="change_logs", verbose_name="Reserva modificada")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, verbose_name="Usuario", null=True, blank=True)
    
    old_arrival = models.DateTimeField(verbose_name="Llegada antigua")
    old_departure = models.DateTimeField(verbose_name="Salida antigua")
    new_arrival = models.DateTimeField(verbose_name="Llegada nueva")
    new_departure = models.DateTimeField(verbose_name="Salida nueva")
    
    old_T = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Antiguo total")
    new_T = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Nuevo total")
    
    paid_dep = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Depósito pagado", default=Decimal("0.00"))
    deposit_topup = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Depósito extra")
    deposit_target = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Nuevo depósito")
    deposit_refund = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Devolución")
    
    old_balance = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Balance antiguo")
    new_balance_due = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal("0.00"), verbose_name="Nuevo balance")
    
    status = models.CharField(max_length=60, choices=LOG_STATUS_CHOICES, verbose_name="Estado", default="pending")
    topup_payment = models.ForeignKey("payments.Payment", on_delete=models.SET_NULL, blank=True, null=True, related_name="change_logs", verbose_name="Pago top up ")
    checkout_session_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="Checkout ID (Stripe)")
    superseded_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")

    class Meta:
        verbose_name="Registro de cambio de reservas"
        verbose_name_plural="Registros de cambio de reservas"

    def __str__(self):
        return f"{self.booking.property.name} - {self.actor} - ({self.new_arrival} => {self.new_departure})"