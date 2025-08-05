from django.db import models
from django.contrib.auth.models import User
from properties.models import Property

# Create your models here.

class Booking(models.Model):
    STATUS_CHOICES = [
    ("pending", "Pendiente"),
    ("confirmed", "Confirmado" ),
    ("cancelled", "Cancelado")
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="bookings")
    person_num = models.IntegerField(verbose_name="Cant.Personas")
    arrival = models.DateTimeField(verbose_name="LLegada")
    departure = models.DateTimeField(verbose_name="Salida")
    status = models.CharField(max_length=20,choices=STATUS_CHOICES, default="pending", verbose_name="Estado")

    class Meta():
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def __str__(self):
        return f"{self.property.name} - {self.user.username} - ({self.arrival} => {self.departure})"