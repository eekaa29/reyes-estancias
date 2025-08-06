from django.shortcuts import render
from django.urls import reverse_lazy
from django.contrib.auth.forms import UserCreationForm
from django.views.generic.edit import CreateView
# Create your views here.
class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/signup.html"

    def get_success_url(self):
        return reverse_lazy("login") + '?register'
