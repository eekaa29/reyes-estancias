from django import forms
from .models import *
from django.core.exceptions import ValidationError
from datetime import timezone, date
from datetime import datetime, time, date, timedelta
from django.utils.timezone import make_aware, is_naive

class ChangeDatesForm(forms.Form):
    checkin = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    checkout = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))

    def clean(self):
        data = super().clean()

        ci = data.get("checkin")
        co = data.get("checkout")
        if not ci or not co:
            raise ValidationError("Fechas inválidas")
        else:
            resta = (co - ci).days

            if resta < 2:
                raise ValidationError("La reserva debe tener una duración mínima de 2 días")
            
            elif co < ci:
                raise ValidationError("La fecha de salida no puede ser inferior a la fecha de llegada")
            
            elif ci < date.today():
                raise ValidationError("La fecha de llegada debe ser posterior al día de hoy")
            
        return data
        


