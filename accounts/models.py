from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+?[0-9]{7,15}$',
    message="Teléfono inválido (7–15 dígitos, + opcional)."
)

class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, validators=[phone_validator], blank=True)

    def __str__(self):
        return self.username