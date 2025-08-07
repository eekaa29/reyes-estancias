from django.shortcuts import render
from django.views.generic.list import ListView
from .models import Booking
from django.contrib.auth.mixins import LoginRequiredMixin
# Create your views here.

class BookingsList(LoginRequiredMixin, ListView):
    login_url = "login"
    model = Booking
    template_name = "bookings/bookings_list.html"

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)