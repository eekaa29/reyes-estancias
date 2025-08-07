from django.urls import path
from .views import BookingsList

urlpatterns = [
    path("bookings_list/", BookingsList.as_view(), name="bookings_list")
]