from django.shortcuts import render
from django.views.generic.list import ListView
from .models import Booking
# Create your views here.

class BookingsList(ListView):
    model = Booking
    template_name = "bookings/bookings_list.html"

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)