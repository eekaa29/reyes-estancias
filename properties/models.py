from django.db import models

# Create your models here.
class Property (models.Model):
    name = models.CharField(verbose_name= "Nombre", max_length=200)
    description = models.TextField(verbose_name="Descripción")
    max_people = models.IntegerField(verbose_name="Capacidad")
    address = models.CharField(max_length= 200, verbose_name="Localización")
    latitude = models.FloatField(blank=True, null= True, verbose_name="Latitud")
    longitude = models.FloatField(blank=True, null= True, verbose_name="Altitud")


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