from django.db import models
from django.utils.timezone import make_aware
from datetime import datetime
# Create your models here.
class Property (models.Model):
    name = models.CharField(verbose_name= "Nombre", max_length=200)
    description = models.TextField(verbose_name="Descripción")
    max_people = models.IntegerField(verbose_name="Capacidad")
    address = models.CharField(max_length= 200, verbose_name="Localización")
    latitude = models.FloatField(blank=True, null= True, verbose_name="Latitud")
    longitude = models.FloatField(blank=True, null= True, verbose_name="Altitud")

    def is_available(self, checkin, checkout, cant_personas):
        checkin = make_aware(datetime.strptime(checkin, "%Y-%m-%d"))
        checkout = make_aware(datetime.strptime(checkout, "%Y-%m-%d"))

        if not checkin or not checkout:
            return False
        
        if self.max_people < int(cant_personas):
            return False
        
        for booking in self.bookings.all():
            if (booking.arrival < checkout) and (booking.departure > checkin):
                return False
        return True

    class Meta():
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return self.name

class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="properties", verbose_name="Imágen")

    def __str__(self):
        return f"Imagen de {self.property.name}"