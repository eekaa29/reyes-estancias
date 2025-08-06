from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from .models import Property
# Create your views here.

class PropertiesList(ListView):
    model = Property
    template_name = "properties/property_list.html"

class PropertyDetail(DetailView):
    model = Property
    template_name = "properties/property_detail.html"
