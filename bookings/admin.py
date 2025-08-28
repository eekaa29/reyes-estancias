from django.contrib import admin
from .models import Booking, BookingChangeLog
# Register your models here.

class AdminBooking(admin.ModelAdmin):
    list_display=("id", "property__name", "user", "arrival", "departure")
    list_filter=("property__name", "user__username", "arrival", "departure")
    readonly_fields=("hold_expires_at",)

class AdminBookingChangeLog(admin.ModelAdmin):
    list_display=("id", "booking__property__name", "actor", "new_arrival", "new_departure")
    list_filter=("actor", "new_arrival", "new_departure")
    readonly_fields=("created_at",)


admin.site.register(Booking, AdminBooking)
admin.site.register(BookingChangeLog, AdminBookingChangeLog)