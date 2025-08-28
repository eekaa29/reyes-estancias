from django.urls import path
from .views import *

urlpatterns = [
    path("bookings_list/", BookingsList.as_view(), name="bookings_list"),
    path("create_booking/<int:property_id>/", CreateBookingView.as_view(), name="create_booking"),
    path("cancel_booking/<int:booking_id>/", CancelBookingView.as_view(), name="cancel_booking"),
    path("cancel_booking_sure/<int:booking_id>/", CancelBookingSureView.as_view(), name="cancel_booking_sure"),
    path("remake_booking/<int:pk>/", RemakeBookingView.as_view(), name="remake_booking"),
    path("change_dates/<int:pk>/", BookingChangeDatesStartView.as_view(), name="booking_change_dates_start"),
    path("change_dates/<int:pk>/preview/", BookingChangeDatesPreviewView.as_view(), name="booking_change_dates_preview"),
    path("change_dates/<int:pk>/apply/", BookingChangeDatesApplyView.as_view(), name="booking_change_dates_apply"),
]