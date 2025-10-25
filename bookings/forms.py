from django import forms
from .models import *
from django.core.exceptions import ValidationError
from datetime import date
from core.forms import TWMixin  # usamos tu mixin existente

class ChangeDatesForm(TWMixin, forms.Form):
    checkin = forms.DateField(
        label="Llegada",
        widget=forms.DateInput(attrs={"type": "text"}),  # necesario para Flatpickr + placeholder
        input_formats=["%Y-%m-%d"],
    )
    checkout = forms.DateField(
        label="Salida",
        widget=forms.DateInput(attrs={"type": "text"}),
        input_formats=["%Y-%m-%d"],
    )

    def clean(self):
        data = super().clean()
        ci, co = data.get("checkin"), data.get("checkout")

        if not ci or not co:
            raise ValidationError("Fechas inválidas")

        days = (co - ci).days
        if days < 2:
            raise ValidationError("La reserva debe tener una duración mínima de 2 noches")
        if co < ci:
            raise ValidationError("La fecha de salida no puede ser anterior a la de llegada")
        if ci < date.today():
            raise ValidationError("La fecha de llegada debe ser posterior al día de hoy")

        return data


