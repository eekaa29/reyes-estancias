from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic import TemplateView
from django.views import View
from .models import *
from properties.models import *
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

class RemakeBookingView(LoginRequiredMixin, View):
    login_url = "login"

    def post(self, request, *args, **kwargs):
        booking = get_object_or_404(Booking, pk=kwargs.get("pk"))
        property = booking.property
        
        if booking.user != self.request.user and not self.request.user.is_staff:
            messages.error = (request, "Usuario no autorizado para rehacer la reserva")
            return redirect("home")

        elif booking.status != "cancelled":
            messages.error(request, "Solo se pueden rehacer reservas canceladas")
            return redirect("bookings_list")

        checkin = booking.arrival
        checkout = booking.departure
        cant_personas = booking.person_num

        total_amount = booking.total_amount
        deposit_amount = booking.deposit_amount
        balance_due = booking.balance_due
        status = "pending"
        stripe_customer_id = booking.stripe_customer_id
        stripe_payment_method_id = booking.stripe_payment_method_id

        #Comprobar si existe una rebooking en curso
        existing = (Booking.objects.filter(user=self.request.user, property=property, arrival=checkin,
                                            departure=checkout, status="cancelled").exclude(hold_expires_at__lt=now()).first())
        
        if existing:
            messages.error(request, "Ya existe un reintento de reserva para esta reserva cancelada")
            return redirect("payment_start", booking_id=existing.id)
        
        if not property.is_available(checkin, checkout, cant_personas):
            messages.error(request, "Las fechas ya no están disponibles")
            return redirect("bookings_list")
        try:
            with transaction.atomic():
                (property.bookings.select_for_update(skip_locked=True)
                .filter(status=["confirmed","pending"]).exclude(hold_expires_at__lt=now())
                .filter(arrival__lt=checkout, departure__gt=checkin).count())

                if not property.is_available(checkin, checkout, cant_personas):
                    messages.error(request, "Las fechas ya no están disponibles")
                    return redirect("bookings_list")
            

                new_booking = Booking.objects.create(
                    user=request.user,
                    property=property,
                    person_num=cant_personas,
                    arrival=checkin,
                    departure=checkout,
                    total_amount=total_amount,
                    deposit_amount=deposit_amount,
                    balance_due=balance_due,
                    status=status,
                    hold_expires_at=now() + timedelta(minutes=30),
                    stripe_customer_id=stripe_customer_id,
                    stripe_payment_method_id=stripe_payment_method_id,
                )
        except Exception as e:
            messages.error(request, f"No es posible rehacer la reserva: {e}")
            return redirect("bookings_list")

        return redirect("payment_start", booking_id=new_booking.id)