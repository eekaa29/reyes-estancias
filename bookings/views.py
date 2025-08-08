from django.shortcuts import render
from django.views.generic.list import ListView
from django.views import View
from .models import Booking
from properties.models import Property
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils.timezone import make_aware
from datetime import datetime
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
            messages.warning("La propiedad ya no está disponible")
            url = f"{redirect("property_detail", args=["property_id"])}?checkin={checkin}&checkout={checkout}&cant_personas={cant_personas}"
            return redirect(url)
        
        checkin = make_aware(datetime.strptime(checkin, "%Y-%m-%d"))
        checkout = make_aware(datetime.strptime(checkout, "%Y-%m-%d"))
        
        booking = Booking.objects.create(
            user = request.user,
            property = property,
            person_num = int(cant_personas),
            arrival = checkin,
            departure = checkout,
            status = "pending"
        )

        messages.success(request, "Reserva creada. Vamos a procesar el pago.")
        return redirect("payment_start", args=["booking.pk"])