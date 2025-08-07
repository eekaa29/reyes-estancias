from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from .models import Property
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
        
        for prop in context["property_list"]:
            prop.available = prop.is_available(checkin, checkout, cant_personas)

        return context 

class PropertyDetail(DetailView):
    model = Property
    template_name = "properties/property_detail.html"
