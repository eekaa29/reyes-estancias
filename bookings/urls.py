from django.urls import path
from .views import BookingsList, CreateBookingView

urlpatterns = [
    path("bookings_list/", BookingsList.as_view(), name="bookings_list"),
    path("create_booking/<int:property_id>", CreateBookingView.as_view(), name="create_booking"),
]