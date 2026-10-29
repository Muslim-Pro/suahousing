import uuid

from django.db import transaction
from django.utils import timezone

from houses.payments import ClickPesaError, send_clickpesa_ussd_push

from .models import Booking


class BookingPaymentError(Exception):
    def __init__(self, message, *, request_may_have_been_sent=False):
        super().__init__(message)
        self.request_may_have_been_sent = request_may_have_been_sent


def initiate_booking_payment(*, booking_id, student, phone_number):
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related(
            'room',
        ).get(pk=booking_id, student=student)
        if booking.status != Booking.STATUS_APPROVED:
            raise BookingPaymentError(
                'Payment is available only after the landlord approves your booking.',
            )
        if booking.payment_status == Booking.PAYMENT_PAID:
            raise BookingPaymentError('This booking has already been paid.')
        if booking.payment_status == Booking.PAYMENT_PENDING:
            raise BookingPaymentError(
                'A payment request is already pending. Check your phone or contact your landlord before trying again.',
                request_may_have_been_sent=True,
            )
        if booking.room.price <= 0:
            raise BookingPaymentError(
                'This room does not have a valid price. Please contact the landlord.',
            )

        order_reference = f'SUA{uuid.uuid4().hex[:8].upper()}'
        # Hifadhi pending kabla ya mtandao ili ombi lingine lisitume push ya pili.
        booking.payment_status = Booking.PAYMENT_PENDING
        booking.payment_reference = order_reference
        booking.payment_phone_number = phone_number
        booking.save(update_fields=[
            'payment_status',
            'payment_reference',
            'payment_phone_number',
            'updated_at',
        ])
        amount = booking.room.price

    try:
        send_clickpesa_ussd_push(
            phone_number=phone_number,
            amount=amount,
            order_reference=order_reference,
        )
    except ClickPesaError as error:
        if not error.request_may_have_been_sent:
            Booking.objects.filter(
                pk=booking_id,
                payment_reference=order_reference,
                payment_status=Booking.PAYMENT_PENDING,
            ).update(
                payment_status=Booking.PAYMENT_UNPAID,
                payment_reference='',
                payment_phone_number='',
                updated_at=timezone.now(),
            )
        # Ikiwa matokeo hayajulikani, pending inazuia malipo yale yale kutumwa tena.
        raise BookingPaymentError(
            str(error),
            request_may_have_been_sent=error.request_may_have_been_sent,
        ) from error

    return order_reference
