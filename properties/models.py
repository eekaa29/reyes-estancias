from django.db import models
from django.utils.timezone import make_aware, now
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from core.tzutils import compose_aware_dt
# Create your models here.

LIMPIEZA = Decimal("100.00")
TAX_IMPUESTOS = Decimal("0.16")

class Property (models.Model):
    name = models.CharField(verbose_name= "Nombre", max_length=200)
    description = models.TextField(verbose_name="Descripción")
    max_people = models.IntegerField(verbose_name="Capacidad")
    nightly_price = models.DecimalField(verbose_name="Precio por Noche", null=True, blank=True, decimal_places=2, max_digits=10)
    address = models.CharField(max_length= 200, verbose_name="Localización")
    latitude = models.FloatField(blank=True, null= True, verbose_name="Latitud")
    longitude = models.FloatField(blank=True, null= True, verbose_name="Altitud")

    def is_available(self, checkin, checkout, cant_personas):
        qs = self.bookings.filter(status__in=["confirmed", "pending"])
        qs = qs.exclude(status="pending", hold_expires_at__lt=now())
        try:
            checkin = compose_aware_dt(checkin,  hour=15, minute=0)  # check-in 15:00
            checkout = compose_aware_dt(checkout, hour=12, minute=0) # check-out 12:00
        except Exception:
            return False
        if not checkin or not checkout:
            return False
        
        if self.max_people < int(cant_personas):
            return False
        
        for booking in qs:
            if (booking.arrival < checkout) and (booking.departure > checkin):
                return False
        return True
    
    def _to_date(self, value):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            value = datetime.strptime(value, "%Y-%m-%d").date()
            return value
        raise ValueError("La fecha seleccionada no es válida")
    
    def quote_total(self, checkin, checkout):
        checkin = self._to_date(checkin)
        checkout = self._to_date(checkout)

        if not checkin or not checkout:
            raise ValueError("Fechas incompletas")
        
        days = (checkout - checkin).days

        if days <= 0:
            raise ValueError("Fechas mal configuradas")

        nightly = self.nightly_price
        if not nightly:
            raise ValueError("Faltan tarifas por configurar")
        

        
        info = {}
        subtotal_base = (nightly * days).quantize(Decimal("0.01"))

        if days >= 30:
            discount_rate = Decimal("0.20")
        
        elif days >= 7:
            discount_rate = Decimal("0.10")
        
        else:
            discount_rate = Decimal("0.00")

        discount_amount = (subtotal_base * discount_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal = (subtotal_base - discount_amount).quantize(Decimal("0.01"))

        taxable = (subtotal + LIMPIEZA).quantize(Decimal("0.01"))
        tax_amount = (taxable * TAX_IMPUESTOS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (taxable + tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        info["days"] = days
        info["nightly"] = nightly
        info["subtotal_base"]= subtotal_base
        info["discount_rate"]= discount_rate
        info["discount_amount"]= discount_amount
        info["subtotal"]= subtotal
        info["cleaning"]= LIMPIEZA
        info["taxable"]= taxable
        info["tax_amount"]= tax_amount
        info["total"]= total
        
        return info

        

    

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