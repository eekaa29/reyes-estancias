from decimal import Decimal, ROUND_HALF_UP
import stripe
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.urls import reverse
from django.db import transaction

from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY

def _to_cents(mx: Decimal) -> int:
    return int((mx * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def ensure_balance_payment(booking):
    with transaction.atomic():
        p = (booking.payments
             .select_for_update()
             .filter(payment_type="balance", status__in=["pending","requires_action"])
             .order_by("-id")
             .first())
        if p:
            if p.amount != booking.balance_due:
                p.amount = booking.balance_due
                p.save(update_fields=["amount"])
            return p

        return Payment.objects.create(
            booking=booking,
            payment_type="balance",
            status="pending",
            amount=booking.balance_due,
            currency="MXN",
        )

def charge_balance_offsession_or_send_checkout(booking, request):
    """
    Intenta cobrar el saldo (70%) off-session. Si falla, crea Checkout Session y envía email con el link.
    Retorna un string corto con el resultado: "succeeded" | "requires_action" | "failed".
    """

    payment = ensure_balance_payment(booking)

    if payment.status == "paid":
        return {"status": "already_paid", "payment": payment}

    if not booking.balance_due or booking.balance_due <= 0:
        return  {"status": "no balance", "payment": payment}
    
    if not (booking.stripe_customer_id and booking.stripe_payment_method_id):
        return {"status": "missing_method", "payment": payment}

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
            # idempotency_key recomendable si llamarás esto desde cron: f"balance-{payment.id}"
        )
        

        payment.stripe_payment_intent_id = intent.id 


        #Si se puede realizar el pago:
        if intent.status == "succeeded":
            payment.status = "paid"
            payment.save(update_fields=["stripe_payment_intent_id", "status"])
            return {"status": "paid", "payment": payment, "intent_id": intent.id}
        
        
        #Si no se puede:
        # Con confirm=True, si no es succeeded casi siempre Stripe lanza excepción.
        # Aun así, si llegas aquí, trata como requiere acción:
        payment.status = "requires_action"
        payment.save(update_fields=["stripe_payment_intent_id", "status"])

    except stripe.error.CardError as e:
        # ⇒ aquí caes cuando necesita 3DS o la tarjeta fue rechazada, porque stripe, en vez de devolver
        # status "requires_action", lanza excepción de CardError.
        #Obtenemos el objeto del error que lanza
        err = getattr(e, "error", None)
        #Dentro del error, suele venir el Payment intent incompleto
        pi = getattr(err, "payment_intent", None)

        # Normalizamos el ID del PaymentIntent (a veces viene dict, a veces objeto)
        pi_id = (pi.get("id") if isinstance(pi, dict) else getattr(pi, "id", None))

        # Si hay ID, lo guardamos en nuestro modelo
        if pi_id:
            payment.stripe_payment_intent_id = pi_id

        # En vez de poner "failed", lo marcamos como "requires_action"
        payment.status = "requires_action"
        payment.save(update_fields=["stripe_payment_intent_id", "status"] if pi_id else ["status"])

        #En caso de que sea algún error real de stripe: Servidor, validación etc...
    except Exception as e:
        payment.status = "failed"
        payment.save(update_fields=["status"])
        return {"status": "failed", "payment": payment, "error": str(e)}
        

    #Si no ha entrado en el if de arriba, significa que no se ha podido realizar el pago,
    #y si no ha entrado en el exept de justo encima, significa que ha dado Card.error
    #Continuamos con el flujo creamos sesión y le mandamos link paga que pague manualmente
    success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
    cancel_url  = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

    session = stripe.checkout.Session.create(
        mode="payment",
        customer=booking.stripe_customer_id,
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
    payment.status = "requires_action"
    payment.stripe_checkout_session_id = session.id
    payment.save(update_fields=["stripe_checkout_session_id", "status"])

    
    #Enviamos email
    context = {
            "user": booking.user,
            "booking": booking,
            "payment_url": session.url #nombre en el template
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
    return {"status": "requires_action", "payment": payment, "checkout_url": session.url}