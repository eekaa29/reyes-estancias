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
from .forms import ChangeDatesForm
from .services import *
from django.http import HttpResponse, HttpResponseBadRequest
from django.db.models import OuterRef, Subquery
from .models import Booking, BookingChangeLog
#from core.tzutils import compose_aware_dt 
# Create your views here.

class BookingsList(LoginRequiredMixin, ListView):
    login_url = "login"
    model = Booking
    template_name = "bookings/bookings_list.html"
    context_object_name="bookings"

    def get_queryset(self):
        latest_log = (BookingChangeLog.objects
                      .filter(booking=OuterRef("pk"))
                      .order_by("-created_at"))
        return (Booking.objects
                .filter(user=self.request.user)  # o tu filtro
                .annotate(last_deposit_refund=Subquery(latest_log.values("deposit_refund")[:1]))
                .select_related("property"))
    
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

        messages.success(request, "Reserva creada.")
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
    
                                                                #CAMBIAR FECHAS

class BookingChangeDatesStartView(LoginRequiredMixin, View):
    login_url="login"
    
    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.user != self.request.user and not self.request.user.is_staff:
            messages.error(request, "Usuario no autorizado")
            return redirect("home")
        
        if booking.status != "confirmed":
            messages.error(request, "Solo se pueden modificar las fechas de reservas confirmadas")
            return redirect("bookings_list")

        form = ChangeDatesForm(initial={
            "checkin": booking.arrival,
            "checkout": booking.departure,
        })

        return render(request, "bookings/change_dates_form.html", {"booking":booking, "form":form})
class BookingChangeDatesPreviewView(LoginRequiredMixin, View):
    login_url="login"

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.user != self.request.user and not self.request.user.is_staff:
            messages.error(request, "Usuario no autorizado")
        
        form = ChangeDatesForm(request.POST)

        if not form.is_valid():
            messages.error(request, "El formulario no es válido")
            return render(request, "change_dates_form.html", {"booking":booking, "form":form})
        
        new_in = compose_aware_dt(form.cleaned_data["checkin"], 15, 0,)
        new_out = compose_aware_dt(form.cleaned_data["checkout"], 12, 0)

        q = quote_change_booking_dates(booking, new_in, new_out)

        if not q["ok"]:
            messages.error(request, "Propiedad no disponible en estas fechas")
            return redirect("change_dates_form.html", {"booking":booking, "form":form})

        ctx = {"booking": booking, "form":form, "quote":q, "checkin":form.cleaned_data["checkin"], "checkout": form.cleaned_data["checkout"]} 
        return render(request, "bookings/change_dates_preview.html", ctx)

class BookingChangeDatesApplyView(LoginRequiredMixin, View):
    login_url="login"

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.user != self.request.user and not self.request.user.is_staff:
            messages.error(request, "Usuario no autorizado")
            return redirect("bookings_list")
        
        
        checkin = request.POST.get("checkin")
        checkout = request.POST.get("checkout")

        try:
            new_in = compose_aware_dt(checkin, 15, 0)
            new_out = compose_aware_dt(checkout, 12, 0)
        except Exception as e:
            messages.error(request,"Formulario inválido")
            print(f"Error: {e}")
            return redirect("booking_change_dates_start", pk=booking.id)


        serv = apply_change_booking_dates(booking=booking, new_in=new_in, new_out=new_out, actor_user=self.request.user, request=request)

        if not serv["ok"]:
            messages.error(request, "No se puedo hacer el cambio de fechas, la disponibilidad cambió")
            return redirect("booking_change_dates_start", pk=booking.id)

        actions = serv.get("actions", {})

        if "checkout_url" in actions:
            messages.info(request, f"El cambio ha sido aplicado, se necesita un depósito adicional de {actions["dep_topup"]} MXN")
            return redirect(actions["checkout_url"])
        
        if "dep_refund" in actions:
            messages.success(request, f"Cambios aplicados. El reembolso ha sido creado: {actions["dep_refund"]} MXN")
            return redirect("bookings_list")
        
        messages.success(request, f"Cambio realizado correctamente. Se ha generado un ajuste en el importe del balance.Todo listo")
        return redirect("bookings_list")