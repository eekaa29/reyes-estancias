from django.shortcuts import render, redirect
from django.views.generic.base import TemplateView
from django.views.generic.edit import FormView
from .forms import HomeSearchForm
from urllib.parse import urlencode

# Create your views here.

class HomeView(FormView):
    template_name = "core/index.html"
    form_class=HomeSearchForm

    def form_valid(self, form):
        cd = form.cleaned_data
        params = urlencode({
            "checkin":cd['checkin'].date(),
            "checkout":cd['checkout'].date(),
            "cant_personas":cd['cant_personas']})
        return redirect(f"properties/property_list/?{params}")
    

class AboutUsView(TemplateView):
    template_name = "core/about_us.html"

class Terms_Cons(TemplateView):
    template_name = "core/terminos_y_condiciones.html"