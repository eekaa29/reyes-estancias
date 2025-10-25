from django.views.generic import CreateView
from django.urls import reverse_lazy
from accounts.forms import SignUpForm

class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/sign_up.html"
    success_url = reverse_lazy("login")
