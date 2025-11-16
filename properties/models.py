from django.db import models
from django.utils.timezone import make_aware, now
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from core.tzutils import compose_aware_dt
from django.db import models, transaction
from django.db.models import Q
# Create your models here.

LIMPIEZA = Decimal("100.00")
TAX_IMPUESTOS = Decimal("0.16")

class Property (models.Model):
    name = models.CharField(verbose_name= "Nombre", max_length=200)
    description = models.TextField(verbose_name="Descripción")
    beds = models.CharField(verbose_name= "Número de camas", max_length=200, default="Cama matrimonial")
    max_people = models.IntegerField(verbose_name="Capacidad")
    nightly_price = models.DecimalField(verbose_name="Precio por Noche", null=True, blank=True, decimal_places=2, max_digits=10)
    address = models.CharField(max_length= 200, verbose_name="Localización")
    latitude = models.FloatField(blank=True, null= True, verbose_name="Latitud")
    longitude = models.FloatField(blank=True, null= True, verbose_name="Altitud")
    airbnb_ical_url = models.URLField("Calendario iCal de Airbnb", blank=True, null=True)

    def is_available(self, checkin, checkout, cant_personas, *, exclude_booking_id=None, buffer_nights=0):
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
        
        if exclude_booking_id:
            qs = qs.exclude(id=exclude_booking_id)

        if buffer_nights:
            checkin -= timedelta(days=buffer_nights)
            checkout += timedelta(days=buffer_nights)


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
    
    def get_blocked_ranges(self):
        """
            Devuelve una lista de tuplas (start_date, end_date) con las fechas bloqueadas
            según el calendario iCal de Airbnb.
        """
        from properties.utils.ical import get_blocked_dates

        if not self.airbnb_ical_url:
            return []
        
        try:
            return get_blocked_dates(self.airbnb_ical_url)
        except Exception as e:
            # Puedes loguearlo o ignorarlo si prefieres
            print(f"[get_blocked_ranges] Error al obtener bloqueos para '{self.name}': {e}")
            return []

        

    

    class Meta():
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return self.name

class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="properties", verbose_name="Imagen")
    cover = models.BooleanField(default=False, db_index=True, verbose_name="Portada")
    position = models.PositiveIntegerField(default=0, help_text="Orden en la galería")

    class Meta:
        ordering = ["position", "id"]
        indexes = [models.Index(fields=["property", "cover"])]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.cover:
            with transaction.atomic():
                PropertyImage.objects.filter(property_id=self.property_id, cover=True)\
                                     .exclude(pk=self.pk).update(cover=False)