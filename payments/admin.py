from django.contrib import admin
from .models import Payment
# Register your models here.
class AdminPayment(admin.ModelAdmin):
    readonly_fields = 'created_at'
admin.site.register(Payment)