from django import forms
from django.core.exceptions import ValidationError
from datetime import datetime, time, date, timedelta
from django.utils.timezone import make_aware, is_naive

class TWMixin:
    base_cls = "mt-1 block w-full rounded-xl border-slate-300 focus:border-blue-600 focus:ring-blue-600"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", self.base_cls)
        placeholders = {"checkin": "Llegada", "checkout": "Salida", "cant_personas": "Huéspedes"}
        for name, field in self.fields.items():
            if name in placeholders:
                field.widget.attrs.setdefault("placeholder", placeholders[name])


class BookingForm(TWMixin, forms.Form):
    checkin = forms.DateField(label="Llegada", widget=forms.DateInput(attrs={"type":"text"}),input_formats=["%Y-%m-%d"],)
    checkout = forms.DateField(label="Salida", widget=forms.DateInput(attrs={"type":"text"}),input_formats=["%Y-%m-%d"],)
    cant_personas = forms.IntegerField(label="Huéspedes", min_value=1)

    def clean(self):
        cleaned = super().clean()

        checkin = cleaned.get("checkin")
        checkout = cleaned.get("checkout")

        if not checkin or not checkout:
            return cleaned
        resta = (checkout - checkin).days
        if resta < 2:
            raise(ValidationError("Cada reserva debe ser de 2 noches o más"))
        if checkout <= checkin:
            raise(ValidationError("La fecha de salida debe ser posterior a la de llegada"))
        elif checkin < date.today():
            raise(ValidationError("La fecha de llegada no puede ser anterior al día de hoy"))

        cleaned["checkin_dt"] = make_aware(datetime.combine(checkin, time(15, 0)))
        cleaned["checkout_dt"] = make_aware(datetime.combine(checkout, time(12, 0)))
        return cleaned
