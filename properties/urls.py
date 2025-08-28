from django.urls import path
from .views import PropertiesList, PropertyDetail

urlpatterns = [
    path("property_list/", PropertiesList.as_view(), name="property_list"),
    path("<int:pk>/", PropertyDetail.as_view(), name="property_detail"),
]