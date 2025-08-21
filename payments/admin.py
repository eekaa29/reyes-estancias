from django.contrib import admin
from .models import Payment, RefundLog
# Register your models here.
class AdminPayment(admin.ModelAdmin):
    list_display = ("id", "booking", "payment_type", "status", "amount", "currency", "created_at")
    list_filter = ("payment_type", "status", "currency", "created_at")
    search_fields = ("booking__property__name", "booking__user__username", "stripe_payment_intent_id", "stripe_checkout_session_id")
    readonly_fields = ("created_at",)

class AdminRefundLog(admin.ModelAdmin):
    list_display=("id", "payment", "amount", "stripe_refund_id", "created_at")
    list_filter=("payment", "stripe_refund_id")
    readonly_fields=("created_at",)

    
admin.site.register(Payment, AdminPayment)
admin.site.register(RefundLog, AdminRefundLog)