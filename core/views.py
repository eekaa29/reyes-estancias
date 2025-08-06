from django.shortcuts import render
from django.views.generic.base import TemplateView

# Create your views here.

class HomeView(TemplateView):
    template_name = "core/index.html"

class AboutUsView(TemplateView):
    template_name = "core/about_us.html"