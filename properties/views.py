from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.shortcuts import redirect
from django.urls import reverse
from .models import Property
from .forms import BookingForm
# Create your views here.

class PropertiesList(ListView):
    model = Property
    template_name = "properties/property_list.html"


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        #Recogo los parametros de la url
        checkin = self.request.GET.get("checkin")
        checkout = self.request.GET.get("checkout")
        cant_personas = self.request.GET.get("cant_personas")

        context["checkin"] = checkin
        context["checkout"] = checkout
        context["cant_personas"] = cant_personas

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


        




