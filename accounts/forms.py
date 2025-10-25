from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User

class TWMixin:
    base = "w-full rounded-xl border border-neutral-300 px-4 py-2 outline-none focus:border-neutral-600 focus:ring-2 focus:ring-neutral-400/40"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = (f.widget.attrs.get("class","") + " " + self.base).strip()
            f.widget.attrs.setdefault("placeholder", f.label)

class SignUpForm(TWMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "phone", "password1", "password2")
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

class StyledAuthenticationForm(TWMixin, AuthenticationForm):
    pass
