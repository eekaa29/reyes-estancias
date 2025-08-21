from django.urls import path
from .views import *

urlpatterns = [
    path("bookings_list/", BookingsList.as_view(), name="bookings_list"),
    path("create_booking/<int:property_id>/", CreateBookingView.as_view(), name="create_booking"),
    path("cancel_booking/<int:booking_id>/", CancelBookingView.as_view(), name="cancel_booking"),
    path("cancel_booking_sure/<int:booking_id>", CancelBookingSureView.as_view(), name="cancel_booking_sure")
]