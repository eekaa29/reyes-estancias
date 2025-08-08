from django import forms
from django.core.exceptions import ValidationError
from datetime import date
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
        '''if is_naive(checkin):
            checkin = make_aware(checkin)
        if is_naive(checkout):
            checkout = make_aware(checkout)'''
        if checkin and checkout:
            if checkout <= checkin:
                raise(ValidationError("La fecha de salida debe ser posterior a la de llegada"))
            elif checkin < date.today():
                raise(ValidationError("La fecha de llegada no puede ser anterior al día de hoy"))
    
        return cleaned
