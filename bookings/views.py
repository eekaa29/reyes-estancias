from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic import TemplateView
from django.views import View
from .models import Booking
from properties.models import Property
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils.timezone import make_aware
from datetime import datetime
from django.urls import reverse
from decimal import Decimal, ROUND_HALF_UP
from core.tzutils import compose_aware_dt
from payments.services import *
#from core.tzutils import compose_aware_dt 
# Create your views here.

class BookingsList(LoginRequiredMixin, ListView):
    login_url = "login"
    model = Booking
    template_name = "bookings/bookings_list.html"

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)
    
class CreateBookingView(LoginRequiredMixin, View):
    login_url = "login"

    def get(self, request, property_id):
        property = get_object_or_404(Property, pk=property_id)
        checkin = request.GET.get("checkin")
        checkout = request.GET.get("checkout")
        cant_personas = request.GET.get("cant_personas")

        if not (checkin and checkout and cant_personas):
            messages.warning("Elija fechas y cantidad de personas")
            return redirect("property_detail", pk=property_id)
        
        if not property.is_available(checkin, checkout, cant_personas):
            messages.warning(request, "La propiedad ya no está disponible")
            url = f"{reverse("property_detail", kwargs={"pk":property_id})}?checkin={checkin}&checkout={checkout}&cant_personas={cant_personas}"
            return redirect(url)
        
        checkin = compose_aware_dt(checkin, hour=15, minute=0)
        checkout = compose_aware_dt(checkout, hour=12, minute=0)

        quote = property.quote_total(checkin.date(), checkout.date())
        total   = quote["total"]
        deposit = (quote["total"] * Decimal("0.30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance = (quote["total"] - deposit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        
        booking, created = Booking.objects.get_or_create(
            user=request.user,
            property=property,
            arrival=checkin,
            departure=checkout,
            defaults={
                "person_num": int(cant_personas),
                "total_amount": total,
                "deposit_amount": deposit,
                "balance_due": balance,
                "status": "pending",
            },
        )
        if not created:
            # si ya existía, sincroniza importes por si estaban en 0
            update_fields = []
            if booking.total_amount != quote["total"]:
                booking.total_amount = quote["total"]; update_fields.append("total_amount")
            if booking.deposit_amount != deposit:
                booking.deposit_amount = deposit; update_fields.append("deposit_amount")
            if booking.balance_due != balance:
                booking.balance_due = balance; update_fields.append("balance_due")
            if update_fields:
                booking.save(update_fields=update_fields)

        messages.success(request, "Reserva creada. Vamos a procesar el pago.")
        return redirect("payment_start", booking_id=booking.id)
    
class CancelBookingView(LoginRequiredMixin, View):
    login_url = "login"

    def post(self, request, booking_id):
        with transaction.atomic():
            booking = (Booking.objects.select_for_update().get(pk=booking_id))

        if self.request.user != booking.user and not self.request.user.is_staff :
            messages.error(request, "Usuario no autorizado")
            return redirect("home")
        
        if booking.status == "cancelled":
            messages.info(request, "La reserva ya estaba cancelada")
            return redirect("bookings_list")
        
        plan = compute_refund_plan(booking)

        booking.status = "cancelled"
        booking.save(update_fields=["status"])

        penalty = plan["penalty"]
        if penalty and penalty > 0:
            #llamo al servicio
            desc = "Penalización cancelación" if plan["penalty_type"] == "cancellation_fee" else "No show"
            charge_offsession_with_fallback(
                booking=booking,
                request=request,
                amount=penalty,
                payment_type=plan["penalty_type"],
                description=f"{desc} · {booking.property.name}",
            )

        def do_refunds():
            if plan["refunds"]:
                for item in plan["refunds"]:
                    refund_payment(item["payment"], item["amount"])

        transaction.on_commit(do_refunds)

        return redirect("bookings_list")
    
class CancelBookingSureView(LoginRequiredMixin, TemplateView):
    template_name="bookings/cancel_booking_sure.html"