from django.shortcuts import render
import stripe
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import make_aware, now, timedelta
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from properties.models import Property
from bookings.models import Booking
from .models import Payment
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .services import *
# Create your views here.

assert settings.STRIPE_SECRET_KEY, "STRIPE_SECRET_KEY no está cargada (None/vacía)"
stripe.api_key = settings.STRIPE_SECRET_KEY
def to_cents(mx_decimal):
    return int(mx_decimal * Decimal("100").quantize(Decimal("1"), rounding=ROUND_HALF_UP))

class StartCheckoutView(LoginRequiredMixin, View):
    #Cobrar el 30%, actualizar modelo Booking y Payments, 
    # crear sesión Stripe y guardar metodo de pago para el 70%
    login_url="login"

    def get(self, request, booking_id):
        booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
        prop = booking.property

        if booking.payments.filter(payment_type="deposit", status="paid"):
            messages.info((request, "El depósito ya está pagado"))
            return redirect("bookings_list")
        
        if booking.hold_expires_at and booking.hold_expires_at <= now():
            messages.info("La reserva ha expirado, vuelve a comprobar disponibilidad")
            return redirect("property_detail", pk=booking.property_id)
        
        if booking.status not in ("pending", "pending"):
            messages.warning(request, "Esta reserva no está en un estado válido para pagar.")
            return redirect("bookings_list")
        
        checkin = booking.arrival.date()
        checkout = booking.departure.date()
        quote = prop.quote_total(checkin, checkout)
        total = quote["total"]
        deposit = (total * Decimal("0.30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance = (total - deposit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        #Completar campos de booking

        fields_to_update = []
        if booking.total_amount != total:
            booking.total_amount = total
            fields_to_update.append("total_amount")
        if booking.deposit_amount != deposit:
            booking.deposit_amount = deposit
            fields_to_update.append("deposit_amount")
        if booking.balance_due != balance:
            booking.balance_due = balance
            fields_to_update.append("balance_due")

        booking.status = "pending"
        fields_to_update.append("status")

        # Mantén un hold para que no te “roben” las fechas mientras paga
        booking.hold_expires_at = now() + timedelta(minutes=30)
        fields_to_update.append("hold_expires_at")

        if fields_to_update:
            booking.save(update_fields=fields_to_update)

        payment = (booking.payments
                .filter(payment_type=["deposit"])
                .order_by("-created_at")
                .first())
        #Crear registro del pago (deposit)
        if payment and payment.status == "paid":
            messages.info(request, "El depósito ya está pagado.")
            return redirect("bookings_list")
        
        if not payment:
            orphan = (booking.payments.filter(payment_type="").order_by("-created_at").first())
            if orphan:
                payment = orphan
                payment.payment_type = "deposit"
                payment.amount = deposit
                payment.currency="MXN"
                payment.status = "pending"
                payment.save(update_fields=["payment_type", "amount", "currency", "status"])

        if not payment or payment.status not in ("pending", "requires_action"):
            payment = Payment.objects.create(
                booking=booking,
                payment_type="deposit",
                status="pending",
                amount=deposit,
                currency="MXN",
            )
        else:
            # Asegura que el amount coincide (por si cambió el precio)
            if payment.amount != deposit:
                payment.amount = deposit
                payment.save(update_fields=["amount"])


        success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
        cancel_url = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

        desc = (
            f"Reserva {prop.name} · {checkin} → {checkout} · {booking.person_num} persona(s) · "
            f"Total ${total} MXN · Anticipo 30%"
        )

        #Preparar la sesion para el 70%(balance) posterior y ejecutar la del 30% actual(deposit)
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=self.request.user.email or None,
            customer_creation="always",
            payment_intent_data={
                "setup_future_usage":"off_session",
                "metadata":{
                    "booking_id": str(booking.id),
                    "payment_id": str(payment.id),
                    "type":"deposit",
                },
            },
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": "mxn",
                    "unit_amount": to_cents(deposit),
                    "product_data": {
                        "name": f"Anticipo reserva · {prop.name}",
                        "description": desc,
                    },
                },
            }],
            metadata={
                "booking_id": str(booking.id),
                "payment_id": str(payment.id),
                "type":"deposit",
            }
        )
        #Actualizamos el modelo payment con la info que acabamos de crear (solo nos faltaba el stripe_payment_intent_id)
        payment.stripe_checkout_session_id = session.id
        payment.save(update_fields=["stripe_checkout_session_id"])

        return redirect(session.url)
    
class CheckoutSuccesView(LoginRequiredMixin, View):
    template_name="payments/success.html"
    def get(self, request):
        booking_id = request.GET.get("booking_id")
        messages.success(request, "Pago realizado correctamente")
        return redirect(reverse("bookings_list"))
    
class CheckoutCancelView(LoginRequiredMixin, View):
    template_name="payments/cancel.html"
    def get(self, request):
        booking_id = request.GET.get("booking_id")
        payment = Payment.objects.filter(booking_id=booking_id).order_by("-created").first()
        if payment and payment.status == "pending":
            payment.status == "failed"
            payment.save(update_fields=["status"])

        try:
            booking = Booking.objects.get(pk=booking_id)
            booking.status = "cancelled"
            booking.save(update_fields=["status"])
            messages.info(request, "Pago fallido, la reserva ha sido cancelada")
        
        except Booking.DoesNotExist:
            messages.info(request, "Operación cancelada")

        return redirect("home")

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid payload or signature")

    etype = event.get("type")
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        session = obj
        booking_id = session.get("metadata", {}).get("booking_id")
        payment_id = session.get("metadata", {}).get("payment_id")
        pi_id = session.get("payment_intent")
        customer_id = session.get("customer")

        if not (booking_id and payment_id and pi_id):
            return HttpResponse(status=200)
        
        pi = stripe.PaymentIntent.retrieve(pi_id, expand=["payment_method"])

        
        
        customer_id = pi.get("customer")
        payment_method_id = (
            pi["payment_method"]["id"] if isinstance(pi.get("payment_method"), dict)
            else pi.get("payment_method")
        )

        try:
            booking = Booking.objects.get(pk=booking_id)
            payment = Payment.objects.get(pk=payment_id, booking=booking)
        except (Booking.DoesNotExist, Payment.DoesNotExist):
            return HttpResponse(status=200)

        # Actualiza estados y guarda credenciales para el 70%
        if payment.status != "succeeded":
            payment.status = "succeeded"
            payment.save(update_fields=["status"])

        update = ["status"]
        if booking.status != "confirmed":
            booking.status = "confirmed"
        if customer_id and booking.stripe_customer_id != customer_id:
            booking.stripe_customer_id = customer_id
            update.append("stripe_customer_id")
        if payment_method_id and booking.stripe_payment_method_id != payment_method_id:
            booking.stripe_payment_method_id = payment_method_id
            update.append("stripe_payment_method_id")
        
        booking.save(update_fields=update)

        
        payment.stripe_payment_intent_id = pi_id
        payment.save(update_fields=["stripe_payment_intent_id"])

    elif etype == "payment_intent.payment_failed":
        pi = obj
        pi_id = pi.get("id")
        payment = Payment.objects.filter(stripe_payment_intent_id=pi_id).select_related("booking").first()
        if payment:
            payment.status = "failed"
            payment.save(update_fields=["status"])

    return HttpResponse(status=200)

class StartBalanceCheckoutView(LoginRequiredMixin, View):
    '''Cobrar el 70% restante'''
    login_url = "login"
    def get(self, request, booking_id):
        booking = get_object_or_404(Booking, pk=booking_id)

        if booking.user != request.user and not request.user.is_staff:
            messages.error(request, "Usuario no autorizado")
            return redirect("home")
        
        if not booking.balance_due or booking.balance_due <=0:
            messages.error(request, "No hay saldo pendiente por cobrar")
            return redirect("booking_detail", kwargs={"pk":"booking_datils"})

        if not (booking.stripe_customer_id and booking.stripe_payment_method_id):
            messages.error(request, "No hay método de pago guardado para ejecutar el pago")
            return redirect("booking_detail", kwargs={"pk":"booking_datils"})
        
        result = charge_balance_offsession_or_send_checkout(booking, request)

        status = result["status"]
        if status == "paid":
            messages.success(request, "Saldo cobrado correctamente.")
            return redirect("bookings_list")

        if status == "requires_action":
            return redirect(result["checkout_url"])

        if status == "already_paid":
            messages.info(request, "El saldo ya estaba pagado.")
            return redirect("bookings_list")

        messages.error(request, "No se pudo cobrar el saldo.")
        return redirect("bookings_list")

class RetryDepositPaymentView(LoginRequiredMixin, View):
    '''Reintento de depósito en caso de fallo'''
    login_url = "login"
    
    def get(self, request, booking_id):
        booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
        prop = booking.property

        existing_paid = booking.payments.filter(payment_type="deposit", status__in=("succeeded", "paid")).exists()

        if existing_paid:
            messages.info(request, "El deposito ya está pagado")
            return redirect("booking_list")
        

        if self.request.user != booking.user and not self.request.user.is_staff:
            messages.error(request, "Usuario no autorizado")
            return redirect("home")
        
        if booking.deposit_amount and booking.deposit_amount <= 0:
            messages.error(request, "No hay cargos de deposito pendientes")
            return redirect("bookings_list")
        
        
        deposit = (booking.deposit_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payment = (booking.payments.filter(payment_type="deposit").order_by("-created_at").first())

        if not payment or payment.status not in ("failed", "requires_action, pending"):
            payment = payment.objects.create(
                booking=booking,
                payment_type = "deposit",
                amount=deposit,
                currency="MXN",
                status = "pending",
            )

        else:
            if payment.amount != deposit:
                payment.amount = deposit
                payment.save(update_fields=["amount"])

        success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
        cancel_url = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

        desc = (
            f"Reserva {prop.name} · {booking.arrival.date()} → {booking.departure.date()} · "
            f"{booking.person_num} persona(s) · Anticipo 30%"
        )


        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=self.request.user.email,
            customer_creation="always",
            payment_intent_data={
                "setup_future_usage":"off_session",
                "metadata":{
                    "booking_id":str(booking.id),
                    "payment_id":str(payment.id),
                    "type":"deposit",
                },
            },
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency":"mxn",
                    "unit_amount": to_cents(deposit),
                    "product_data": {
                        "name": f"Anticipo reserva · {prop.name}",
                        "description": desc,
                    },
                },
            }],
            metadata={
                "booking_id": str(booking.id),
                "payment_id": str(payment.id),
                "type": "deposit",
            },
        )
        payment.stripe_checkout_session_id = session.id
        payment.stripe_payment_intent_id = session.payment_intent
        payment.status= "pending"
        payment.save(update_fields=["stripe_checkout_session_id", "stripe_payment_intent_id", "status"])
       
        return redirect("session.url")




class RetryBalancePaymentView(LoginRequiredMixin, View):
    '''Si el primer off-session falla, creo sesión para que el cliente haga el pago manual'''
    login_url = "login"

    def get(self, request, booking_id):
        booking = get_object_or_404(Booking, pk=booking_id)

        if not self.request.user == booking.user and not self.request.user.is_staff:
            messages.error(request, "No autorizado")
            return redirect("home")
        if not booking.balance_due or booking.balance_due <= 0 or booking.payments.filter(payment_type="balance", status="paid").exists():
            messages.error(request, "No hay saldo por cobrar")
            return redirect(reverse("booking_datail", kwargs={"pk": booking.id}))

        base_url = request.build_absolute_uri("/").rstrip("/")
        success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
        cancel_url = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

        session = stripe.checkout.Session.create(
            mode="payment",
            customer=booking.stripe_customer_id,
            customer_email=booking.user.email,
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[{
                "quantity":1,
                "price_data":{
                    "currency":"mxn",
                    "unit_amount":to_cents(booking.balance_due),
                    "product_data":{
                        "name": f"Saldo reserva · {booking.property.name}",
                        "description": f"Booking #{booking.id} — {booking.arrival.date()} → {booking.departure.date()}",
                    },
                },
            }],
            metadata={
                "booking_id": booking.id,
                "type": "balance",
            },
        )



def expire_unpaid_bookings():
    qs = Booking.objects.filter(status="pending", hold_expires_at__isnull=False, hold_expires_at_lt=now())
    updated = qs.update(status="expired")
    return updated

