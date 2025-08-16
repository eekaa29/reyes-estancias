from decimal import Decimal, ROUND_HALF_UP
import stripe
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.urls import reverse

from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY

def _to_cents(mx: Decimal) -> int:
    return int((mx * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def charge_balance_offsession_or_send_checkout(booking, request_base_url: str) -> str:
    """
    Intenta cobrar el saldo (70%) off-session. Si falla, crea Checkout Session y envía email con el link.
    Retorna un string corto con el resultado: "succeeded" | "requires_action" | "failed".
    """

    if not booking.balance_due or booking.balance_due <= 0:
        return "No hay saldo a cobrar"
    
    payment= Payment.objects.create(
        booking=booking,
        payment_type="balance",
        amount=booking.balance_due,
        currency="MXN",
        status="pending",
    )

    try:
        intent = stripe.PaymentIntent.create(
            amount=_to_cents(booking.balance_due),
            currency="mxn",
            customer=booking.stripe_customer_id,
            payment_method=booking.stripe_payment_method_id,
            off_session=True,
            confirm=True,
            metadata={
                "booking_id": str(booking.id),
                "payment_id": str(payment.id),
                "type":"balance"
            },
            description=f"Pago post checkin {booking.property.name}",
        )
        payment.stripe_payment_intent_id = intent.id 
        #Si se puede realizar el pago:
        if intent.status == "succeeded":
            payment.status = "paid"
            payment.save(update_fields=["stripe_payment_intent_id", "status"])
            return "succeeded"
        
        
        #Si no se puede:
        payment.status = "pending"
        payment.save(update_fields=["stripe_payment_intent_id", "status"])
        

    except stripe.error.CardError:
        # fallo duro (tarjeta rechazada, etc.)
        payment.status = "failed"
        payment.save(update_fields=["status"])

    #Si no ha entrado en el if de arriba, significa que no se ha podido realizar el pago,
    #  creamos sesión y le mandamos link paga que pague manualmente

    success_url = f"{request_base_url}{reverse('payment_success')}?booking_id={booking.id}"
    cancel_url  = f"{request_base_url}{reverse('payments_cancel')}?booking_id={booking.id}"

    session = stripe.checkout.Session.create(
        mode="payment",
        customer=booking.stripe_customer_id or None,
        customer_email=booking.user.email or None,
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "mxn",
                "unit_amount": _to_cents(booking.balance_due),
                "product_data": {
                    "name": f"Segundo pago · {booking.property.name}",
                    "description": f"Booking #{booking.id} — {booking.arrival.date()} → {booking.departure.date()}",
                },
            },
        }],
        metadata={"booking_id": str(booking.id), "payment_id": str(payment.id), "type": "balance"},
    )
    payment.stripe_payment_intent_id = session.payment_intent
    payment.stripe_checkout_session_id = session.id
    payment.save(update_fields=["stripe_payment_intent_id", "stripe_checkout_session_id"])

    
    #Enviamos email
    context = {
            "user": booking.user,
            "booking": booking,
            "payment_url": session.url
    }

    subject = f"Completa el pago fallido de la reserva {booking.property.name}"
    html_body = render_to_string("emails/retry_balance_payment.html", context)
    send_mail(
        subject=subject,
        message="Para completar tu pago haz click en el enlace (HTML only).",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[booking.user.email],
        html_message=html_body,
        fail_silently=False,
    )

    return "requires action"