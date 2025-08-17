from django.urls import path, include
from .views import HomeView, AboutUsView, Terms_Cons

urlpatterns = [
    path("", HomeView.as_view(),name="home"),
    path("about_us", AboutUsView.as_view(), name = "about_us"),
    path("terminos_y_condiciones", Terms_Cons.as_view(), name = "terminos_y_condiciones"),

]