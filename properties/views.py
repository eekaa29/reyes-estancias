from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from .models import Property, PropertyImage
from .forms import BookingForm
from bookings.models import Booking
from django.db.models import Prefetch
# Create your views here.

class PropertiesList(ListView):
    model = Property
    template_name = "properties/property_list.html"
    context_object_name = "property_list"

    def get_queryset(self):
        cover_prefetch = Prefetch(
            "images",
            queryset=PropertyImage.objects.filter(cover=True)
                     .only("id", "image", "property"),
            to_attr="cover_list",
        )
        all_prefetch = Prefetch(
            "images",
            queryset=PropertyImage.objects.order_by("position", "id")
                     .only("id", "image", "property"),
            to_attr="all_images",
        )
        return (
            Property.objects.all()
            .prefetch_related(cover_prefetch, all_prefetch)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkin = self.request.GET.get("checkin")
        checkout = self.request.GET.get("checkout")
        cant_personas = self.request.GET.get("cant_personas")

        context["checkin"] = checkin
        context["checkout"] = checkout
        context["cant_personas"] = cant_personas

        if checkin and checkout and cant_personas:
            for prop in context["property_list"]:
                prop.available = prop.is_available(checkin, checkout, cant_personas)
        else:
            for prop in context["property_list"]:
                prop.available = None

        return context 

class PropertyDetail(DetailView):
    model = Property
    template_name = "properties/property_detail.html"
    context_object_name = "property"
    success_url = reverse_lazy("bookings_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        #Recogo los parametros de la url
        checkin = self.request.GET.get("checkin")
        checkout = self.request.GET.get("checkout")
        cant_personas = self.request.GET.get("cant_personas")

        context["checkin"] = checkin
        context["checkout"] = checkout
        context["cant_personas"] = cant_personas

        #Localizar la reserva y su pago de depósito por si falla

        context["active_booking"] = None
        context["deposit_payment"] = None

        if self.request.user.is_authenticated:
            booking_id = self.request.GET.get("booking_id")

            base_qs = Booking.objects.filter(user=self.request.user, 
            property=self.object).order_by("-id").prefetch_related("payments")

            if booking_id:
                booking = base_qs.filter(pk=booking_id).first()
            else:
                booking = base_qs.filter(status__in=["pending", "confirmed"]).first()
            
            if booking:
                context["active_booking"] = booking
                deposit = (booking.payments.filter(payment_type="deposit").order_by("-id").first())
                context["deposit_payment"] = deposit
                return context
            

        #Caso 1- Viene del botón "Reservar ahora"
        if checkin and checkout and cant_personas:
            context["available"] = self.object.is_available(checkin, checkout, cant_personas)
            #Form precargado por si quiere cambiar fechas
            context["form"] = BookingForm(initial={"checkin" : checkin, "checkout" : checkout, "cant_personas" : cant_personas})
        else:
            #Caso 2- No ha completado el form del home, mostramos el form
            context["available"] = None
            context["form"] = BookingForm()
        return context
    
    #El usuario completa el formulario:
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = BookingForm(request.POST)
        #Si es válido
        if form.is_valid():
            checkin = form.cleaned_data["checkin"]
            checkout = form.cleaned_data["checkout"]
            cant_personas = form.cleaned_data["cant_personas"]
            # Redirige a la misma detail con los params en la URL (GET)
            url = f"{reverse('property_detail', args=[self.object.pk])}?checkin={checkin}&checkout={checkout}&cant_personas={cant_personas}"
            return redirect(url)
        #Si no es válido
        else:
            context = self.get_context_data()
            context["form"] = form
            return self.render_to_response(context)


        




