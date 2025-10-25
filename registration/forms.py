from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()
class TWMixin:
    base = "w-full rounded-xl border border-neutral-300 px-4 py-2 outline-none focus:border-neutral-600 focus:ring-2 focus:ring-neutral-400/40"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = (f.widget.attrs.get("class","") + " " + self.base).strip()
            f.widget.attrs.setdefault("placeholder", f.label)

class UserCreationFormWithEmail(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Requerido, debe ser único")

    class Meta():
        model = User
        fields = ("username", "email", "phone", "password1", "password2")
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("El email introducido ya existe, prueba con otro")
        return email