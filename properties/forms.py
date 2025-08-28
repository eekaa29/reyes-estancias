from django import forms
from django.core.exceptions import ValidationError
from datetime import date, timedelta
from django.utils.timezone import make_aware, is_naive

class BookingForm(forms.Form):
    checkin = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    checkout = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    cant_personas = forms.IntegerField(min_value=1, label="cant_personas")

    def clean(self):
        cleaned = super().clean()

        checkin = cleaned.get("checkin")
        checkout = cleaned.get("checkout")

        if not checkin or not checkout:
            return cleaned
        if checkin and checkout:
            resta = (checkout - checkin).days
            if resta < 2:
                raise(ValidationError("Cada reserva debe ser de 2 noches o más"))
            if checkout <= checkin:
                raise(ValidationError("La fecha de salida debe ser posterior a la de llegada"))
            elif checkin < date.today():
                raise(ValidationError("La fecha de llegada no puede ser anterior al día de hoy"))
    
        return cleaned
