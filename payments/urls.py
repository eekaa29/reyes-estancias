from django.urls import path
from .views import StartCheckoutView, CheckoutSuccesView, CheckoutCancelView, StartBalanceCheckoutView, RetryBalancePaymentView, stripe_webhook, RetryDepositPaymentView
from . import views

urlpatterns = [
    path("payment_start/<int:booking_id>/", StartCheckoutView.as_view(), name="payment_start"),
    path("balance_start/<int:booking_id>/", StartBalanceCheckoutView.as_view(), name="start_balance"),
    path("payment_success/", CheckoutSuccesView.as_view(), name="payment_success"),
    path("payment_cancel/", CheckoutCancelView.as_view(), name="payment_cancel"),
    path("webhook/", views.stripe_webhook, name="webhook"),
    path("retry-balance/<int:booking_id>/", RetryBalancePaymentView.as_view(), name="retry_balance"),
    path("retry-deposit/<int:booking_id>/", RetryDepositPaymentView.as_view(), name="retry_deposit"),
]