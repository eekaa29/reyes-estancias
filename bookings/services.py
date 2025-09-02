from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.db import transaction
from properties.models import Property
from payments.services import *
from .models import *



DEPOSIT_RATE = Decimal("0.30")

def _round(num):
    return num.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def compute_price(property, checkin, checkout):
    price = property.quote_total(checkin, checkout)
    return price["total"]

def quote_change_booking_dates(booking, new_in, new_out):
    property = booking.property
    T_old = _round(booking.total_amount)
    T_new = _round(compute_price(property, new_in, new_out))
    paid_dep = get_paid_deposit_amount(booking)

    if not property.is_available(new_in, new_out, booking.person_num,
        exclude_booking_id=booking.id, buffer_nights=0):
        return {"ok": False, "reason": "not_available"}
    
    dep_topup = Decimal("0.00")
    dep_refund = Decimal("0.00")

    if T_new >= T_old:
        deposit_target = _round(T_new * DEPOSIT_RATE)
        if paid_dep < deposit_target:
            dep_topup = _round(deposit_target - paid_dep)
        balance_next = _round(T_new - (paid_dep + dep_topup))
    else:
        if paid_dep > T_new:
            dep_refund = _round(paid_dep - T_new)
            balance_next = Decimal("0.00")
        else:
            balance_next = _round(T_new - paid_dep)

    return {
        "ok": True,
        "preview": True,
        "T_new": T_new,
        "dep_topup": dep_topup,
        "dep_refund": dep_refund,
        "balance_next": balance_next,
        "deposit_target": _round(T_new * DEPOSIT_RATE),
    }

def apply_change_booking_dates(booking, new_in, new_out, *, actor_user, request=None):
    
    quote = quote_change_booking_dates(booking, new_in, new_out)

    if not quote["ok"]:
        return quote
    
    property = booking.property
    old_in = booking.arrival
    old_out = booking.departure
    old_balance = booking.balance_due
    old_total = booking.total_amount

    with transaction.atomic():
        Property.objects.select_for_update().get(pk=property.pk)
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        
        if not property.is_available(new_in, new_out, booking.person_num, exclude_booking_id=booking.id, buffer_nights=0):
            return {"ok": False, "msg" : "Propiedad no disponible"}
    
        paid_dep = get_paid_deposit_amount(booking)

        actions = {}
        # Caso A: hay top-up => NO tocamos Booking hasta pagar
        if quote["dep_topup"] > 0:
            # invalida logs pendientes previos (misma reserva)
            BookingChangeLog.objects.filter(
                booking=booking,
                status="pending"
            ).update(status="superseded", superseded_at=now())
            
            clog = BookingChangeLog.objects.create(
            booking=booking,
            actor=actor_user,
            old_arrival=old_in,
            old_departure=old_out,
            new_arrival=new_in,
            new_departure=new_out,
            old_T=_round(old_total),
            new_T=_round(quote["T_new"]),
            paid_dep=_round(paid_dep),
            deposit_topup=_round(quote["dep_topup"]),
            deposit_target=_round(quote["deposit_target"]),
            deposit_refund=_round(quote["dep_refund"]),
            old_balance=_round(old_balance),
            new_balance_due=_round(quote["T_new"] - (get_paid_deposit_amount(booking) + quote["dep_topup"])),
            status="pending",
        )
            # crea top-up y guarda IDs en el log
            top = create_deposit_topup_checkout(
                            booking, request, quote["dep_topup"],
                            description="Depósito adicional para el cambio de fechas",
                            change_log_id=clog.id,  # << clave
                        )
            
            if top["status"] == "pending":
                    pay = top["payment"]
                    clog.topup_payment = pay
                    clog.checkout_session_id = pay.stripe_checkout_session_id
                    clog.save(update_fields=["topup_payment", "checkout_session_id"])
                    actions.update({"dep_topup": quote["dep_topup"], "checkout_url": top["checkout_url"]})
            return {"ok": True, "actions": actions, "T_new": quote["T_new"], "balance_next": booking.balance_due}

        # Caso B: SIN top-up (puede haber refund) => aplicamos ya
        booking.arrival=new_in
        booking.departure=new_out
        booking.total_amount=_round(quote["T_new"])
        booking.deposit_amount=_round(quote["deposit_target"])
        paid_dep = get_paid_deposit_amount(booking)
        booking.balance_due=_round(max(quote["T_new"] - paid_dep, Decimal("0.00")))
        booking.save(update_fields=["arrival", "departure", "total_amount", "deposit_amount", "balance_due"])

        #Aplicamos ETA del cobro del balance off-session
        when = booking.arrival + timedelta(days=2)
        reschedule_balance_charge(booking, when)
        
        clog = BookingChangeLog.objects.create(
            booking=booking,
            actor=actor_user,
            old_arrival=old_in,
            old_departure=old_out,
            new_arrival=new_in,
            new_departure=new_out,
            old_T=_round(old_total),
            new_T=_round(quote["T_new"]),
            paid_dep=_round(paid_dep),
            deposit_topup=_round(quote["dep_topup"]),
            deposit_target=_round(quote["deposit_target"]),
            deposit_refund=_round(quote["dep_refund"]),
            old_balance=_round(old_balance),
            new_balance_due=_round(booking.balance_due),
            status="applied",
        )
        actions = {}
        if quote["dep_refund"] > 0:
            refund = trigger_refund_for_deposit_diff(booking, quote["dep_refund"])
            actions.update({"dep_refund":quote["dep_refund"], "refund_result":refund})
                
            

        reschedule_balance_charge(booking, when=booking.arrival + timedelta(days=2))

    return {"ok": True, "actions": actions, "T_new": quote["T_new"], "balance_next": booking.balance_due}

