from django.urls import path, include
from .views import HomeView, AboutUsView

urlpatterns = [
    path("", HomeView.as_view(),name="home"),
    path("about_us", AboutUsView.as_view(), name = "about_us")
]