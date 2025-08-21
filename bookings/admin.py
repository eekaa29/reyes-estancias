from django.contrib import admin
from .models import Booking
# Register your models here.

class AdminBooking(admin.ModelAdmin):
    list_display=("id", "property__name", "user", "arrival", "departure")
    list_filter=("property__name", "user__username", "arrival", "departure")
    readonly_fields=("hold_expires_at",)

admin.site.register(Booking, AdminBooking)