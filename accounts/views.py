import threading
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.template.loader import render_to_string

from houses.models import House, Room

from .forms import (
    CustomPasswordResetForm,
    BookingPaymentForm,
    BookingMessageForm,
    HouseReportForm,
    LandlordApplicationForm,
    LandlordHouseForm,
    LandlordPasswordChangeForm,
    LandlordRoomForm,
    ProfilePicForm,
    ReviewForm,
    SavedSearchForm,
    StudentDetailsForm,
    SupportRequestForm,
    UserRegisterForm,
)
from .models import (
    Booking,
    BookingMessage,
    HouseReport,
    LandlordApplication,
    Profile,
    Review,
    SavedHouse,
    SavedSearch,
    StudentNotification,
    SupportRequest,
)
from .receipts import build_payment_receipt_pdf
from .services import BookingPaymentError, initiate_booking_payment
from .utils import tanzania_whatsapp_number


class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.txt'
    html_email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')


def _send_email_background(subject, text_content, html_content, recipient_list):
    """Tuma email nyuma ili request ya mtumiaji isingoje SMTP (Render timeout)."""
    try:
        msg = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
        )
        msg.attach_alternative(html_content, 'text/html')
        msg.send(fail_silently=True)
    except Exception:
        pass


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()

            username = form.cleaned_data.get('username')
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            email = form.cleaned_data.get('email')
            login_url = request.build_absolute_uri('/accounts/login/')

            subject = f'Welcome {first_name}! Your Account is Ready'
            # 🏠
            context = {
                'first_name': first_name,
                'last_name': last_name,
                'username': username,
                'login_url': login_url,
                'support_email': settings.SUPPORT_EMAIL,
            }

            html_content = render_to_string('emails/welcome.html', context)
            text_content = (
                f"Hello {first_name},\n\n"
                f"Welcome to SUA Student Housing! Your registration has been completed.\n"
                f"Your username: {username}\n"
                f"Log in here: {login_url}\n\n"
                f"SUA Student Housing Team"
            )

            # Usisubiri Gmail: tuma email kwenye thread ili usajili usife 500 kwenye Render
            threading.Thread(
                target=_send_email_background,
                args=(subject, text_content, html_content, [email]),
                daemon=True,
            ).start()

            messages.success(
                request,
                f'Welcome {first_name}! Your account has been created successfully. You can log in now.'
            )
            return redirect('login')

        # messages.error(request, 'Please correct the errors in the form before proceeding.')
    else:
        form = UserRegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


class CustomLoginView(LoginView):
    """Baada ya login, mpeleke mtumiaji kwenye dashboard ya aina yake."""

    def form_valid(self, form):
        response = super().form_valid(form)
        jina = self.request.user.get_full_name() or self.request.user.username
        messages.success(self.request, f'Welcome back, {jina}!')
        return response

    def get_success_url(self):
        next_url = self.get_redirect_url()
        if next_url:
            return next_url
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        if profile.user_type == 'landlord':
            return reverse('landlord_dashboard')
        return reverse('student_dashboard')


class CustomLogoutView(LogoutView):
    """Logout yenye toast ya success kwenye ukurasa unaofuata."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.success(request, 'You have been logged out successfully.')
        return super().dispatch(request, *args, **kwargs)


def _ensure_landlord(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'landlord':
        messages.error(request, 'This page is available to landlords only.')
        return None
    return profile


@login_required
def landlord_dashboard(request):
    profile = _ensure_landlord(request)
    if profile is None:
        return redirect('home')

    houses = (
        House.objects.filter(landlord=request.user)
        .prefetch_related('rooms')
        .order_by('-created_at')
    )
    rooms = Room.objects.filter(house__landlord=request.user)
    landlord_bookings = Booking.objects.filter(
        room__house__landlord=request.user,
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
    ).select_related('student', 'student__profile', 'room', 'room__house').prefetch_related('messages__sender')
    notifications = StudentNotification.objects.filter(recipient=request.user)
    unread_message_count = notifications.filter(
        is_read=False,
        notification_type__in=[
            StudentNotification.TYPE_MESSAGE,
            StudentNotification.TYPE_STUDENT_MESSAGE,
        ],
    ).count()

    context = {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
        'password_form': LandlordPasswordChangeForm(user=request.user),
        'houses': houses[:10],
        'total_properties': houses.count(),
        'available_property_rooms': rooms.filter(house__is_available=True).count(),
        'unavailable_property_rooms': rooms.filter(house__is_available=False).count(),
        'open_password_modal': False,
        'pending_bookings': landlord_bookings.filter(status=Booking.STATUS_PENDING)[:20],
        'landlord_bookings': landlord_bookings[:50],
        'pending_booking_count': landlord_bookings.filter(status=Booking.STATUS_PENDING).count(),
        'unread_message_count': unread_message_count,
        'pending_payment_confirmation_count': landlord_bookings.filter(
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_PENDING,
        ).count(),
        'notifications': notifications[:8],
        'unread_notification_count': notifications.filter(is_read=False).count(),
    }
    return render(request, 'accounts/landlord_dashboard.html', context)


@login_required
def student_dashboard(request):
    # Kusanya listings, bookings, saved homes na taarifa kwa mwanafunzi huyu pekee.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type == 'landlord':
        return redirect('landlord_dashboard')
    landlord_application = LandlordApplication.objects.filter(profile=profile).first()

    available_houses = House.objects.filter(is_available=True)
    recent_houses = (
        available_houses.annotate(
            room_count=Count('rooms'),
            minimum_price=Min('rooms__price'),
        )
        .order_by('-created_at')[:3]
    )
    bookings = (
        Booking.objects.filter(student=request.user)
        .select_related('room', 'room__house', 'room__house__landlord', 'room__house__landlord__profile')
        .prefetch_related('messages__sender')
    )
    booking_list = list(bookings[:10])
    for booking in booking_list:
        landlord_phone = booking.room.house.landlord.profile.phone
        booking.landlord_whatsapp = tanzania_whatsapp_number(landlord_phone)
        booking.conversation = booking.messages.order_by('created_at')
        booking.has_review = Review.objects.filter(booking=booking).exists()
    saved_houses = SavedHouse.objects.filter(
        student=request.user,
    ).select_related('house')
    saved_search_list = list(SavedSearch.objects.filter(student=request.user)[:5])
    for saved_search in saved_search_list:
        room_filters = {'house__is_available': True}
        query_params = {}
        if saved_search.location:
            room_filters['house__location'] = saved_search.location
            query_params['location'] = saved_search.location
        if saved_search.room_type:
            room_filters['room_type'] = saved_search.room_type
            query_params['room_type'] = saved_search.room_type
        if saved_search.minimum_price is not None:
            room_filters['price__gte'] = saved_search.minimum_price
            query_params['min_price'] = saved_search.minimum_price
        if saved_search.maximum_price is not None:
            room_filters['price__lte'] = saved_search.maximum_price
            query_params['max_price'] = saved_search.maximum_price
        matching_rooms = Room.objects.filter(
            **room_filters,
        ).exclude(
            booking_requests__status=Booking.STATUS_APPROVED,
        ).select_related('house').distinct().order_by('price')
        saved_search.matching_room_count = matching_rooms.count()
        saved_search.matching_rooms = list(matching_rooms[:3])
        saved_search.results_url = (
            f'{reverse("available_rooms")}?{urlencode(query_params)}#listings'
        )
    notifications = StudentNotification.objects.filter(
        recipient=request.user,
    )
    support_requests = SupportRequest.objects.filter(student=request.user)
    context = {
        'profile': profile,
        'available_house_count': available_houses.count(),
        'available_room_count': Room.objects.filter(
            house__is_available=True,
        ).count(),
        'recent_houses': recent_houses,
        'saved_houses': saved_houses[:6],
        'saved_house_count': saved_houses.count(),
        'saved_searches': saved_search_list,
        'bookings': booking_list,
        'saved_house_ids': list(
            saved_houses.values_list('house_id', flat=True),
        ),
        'active_booking_count': bookings.filter(
            status=Booking.STATUS_APPROVED,
        ).count(),
        'pending_booking_count': bookings.filter(
            status=Booking.STATUS_PENDING,
        ).count(),
        'notifications': notifications[:8],
        'unread_notification_count': notifications.filter(is_read=False).count(),
        'recent_activity': notifications[:5],
        'support_requests': support_requests[:5],
        'open_support_request_count': support_requests.filter(
            status=SupportRequest.STATUS_OPEN,
        ).count(),
        'support_form': SupportRequestForm(),
        'landlord_application': landlord_application,
    }
    return render(request, 'accounts/student_dashboard.html', context)


@login_required
def save_search(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != Profile.TYPE_STUDENT:
        messages.error(request, 'Only students can save housing searches.')
        return redirect('landlord_dashboard')
    if request.method != 'POST':
        return redirect('available_rooms')

    form = SavedSearchForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please check the filters and try saving the search again.')
        return _saved_search_return_url(request)

    search_data = form.cleaned_data
    existing_searches = SavedSearch.objects.filter(
        student=request.user,
        location=search_data['location'],
        room_type=search_data['room_type'],
    )
    for field in ('minimum_price', 'maximum_price'):
        value = search_data[field]
        if value is None:
            existing_searches = existing_searches.filter(**{f'{field}__isnull': True})
        else:
            existing_searches = existing_searches.filter(**{field: value})

    if existing_searches.exists():
        messages.info(request, 'You have already saved these filters.')
    else:
        with transaction.atomic():
            saved_search = form.save(commit=False)
            saved_search.student = request.user
            saved_search.save()
            old_search_ids = list(
                SavedSearch.objects.filter(student=request.user)
                .order_by('-created_at')
                .values_list('pk', flat=True)[5:]
            )
            SavedSearch.objects.filter(pk__in=old_search_ids).delete()
        messages.success(request, 'Search saved. Matching room counts update as availability changes.')
    return _saved_search_return_url(request)


def _saved_search_return_url(request):
    candidate = request.POST.get('next', '')
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(candidate)
    return redirect('student_dashboard')


@login_required
def delete_saved_search(request, pk):
    if request.method == 'POST':
        saved_search = get_object_or_404(SavedSearch, pk=pk, student=request.user)
        saved_search.delete()
        messages.success(request, 'Saved search removed.')
    return redirect('student_dashboard')


@login_required
def apply_for_landlord(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type == 'landlord':
        return redirect('landlord_dashboard')

    # Ofa inayosubiri haiwezi kutumwa mara nyingi; lililokataliwa linaweza kufanyiwa marekebisho.
    application = LandlordApplication.objects.filter(profile=profile).first()
    if application and application.status == LandlordApplication.STATUS_PENDING:
        if request.method == 'POST':
            messages.info(request, 'Your landlord application is already awaiting review.')
            return redirect('student_dashboard')
        return render(request, 'accounts/landlord_application.html', {
            'application': application,
            'form': None,
        })

    form = LandlordApplicationForm(
        request.POST if request.method == 'POST' else None,
        profile=profile,
        instance=application,
    )
    if request.method == 'POST' and form.is_valid():
        application = form.save(commit=False)
        # Kila kutuma upya huanza review mpya na kuondoa maelezo ya uamuzi wa zamani.
        application.status = LandlordApplication.STATUS_PENDING
        application.admin_note = ''
        application.reviewed_at = None
        application.reviewed_by = None
        with transaction.atomic():
            profile.phone = form.cleaned_data['phone'].strip()
            profile.save(update_fields=['phone'])
            application.save()
        messages.success(request, 'Your landlord application was submitted for review.')
        return redirect('student_dashboard')

    return render(request, 'accounts/landlord_application.html', {
        'application': application,
        'form': form,
    })


@login_required
def booking_payment_receipt(request, pk):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type == 'landlord':
        return redirect('landlord_dashboard')

    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update().select_related(
                'student',
                'room',
                'room__house',
                'room__house__landlord',
            ),
            pk=pk,
            student=request.user,
        )
        if booking.payment_status != Booking.PAYMENT_PAID:
            messages.info(
                request,
                'Receipt is available only after the landlord confirms that payment has been received.',
            )
            return redirect('student_dashboard')

        if booking.receipt_verification_token is None:
            booking.receipt_verification_token = uuid.uuid4()
            booking.save(update_fields=['receipt_verification_token'])

    receipt_number = booking.payment_reference or f'SUA-{booking.pk:04d}'
    verification_url = request.build_absolute_uri(
        reverse(
            'verify_payment_receipt',
            kwargs={'token': booking.receipt_verification_token},
        ),
    )
    response = HttpResponse(
        build_payment_receipt_pdf(
            booking=booking,
            receipt_number=receipt_number,
            verification_url=verification_url,
        ),
        content_type='application/pdf',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="payment-receipt-{receipt_number}.pdf"'
    )
    return response


def verify_payment_receipt(request, token):
    booking = get_object_or_404(
        Booking.objects.select_related('room', 'room__house'),
        receipt_verification_token=token,
        payment_status=Booking.PAYMENT_PAID,
    )
    return render(request, 'accounts/verify_payment_receipt.html', {
        'booking': booking,
        'receipt_number': booking.payment_reference or f'SUA-{booking.pk:04d}',
    })


@login_required
def landlord_add_property(request):
    profile = _ensure_landlord(request)
    if profile is None:
        return redirect('home')

    form = LandlordHouseForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        # Weka mwenye nyumba kutoka kwenye akaunti iliyoingia, si kwenye data ya form.
        house = form.save(commit=False)
        house.landlord = request.user
        house.save()
        messages.success(request, f'"{house.title}" has been added.')
        return redirect('landlord_dashboard')

    return render(request, 'accounts/landlord_form.html', {
        'form': form,
        'page_title': 'Add a property',
        'page_description': 'Add your property details so students can discover it.',
        'submit_label': 'Save property',
        'has_properties': True,
    })


@login_required
def landlord_add_room(request):
    profile = _ensure_landlord(request)
    if profile is None:
        return redirect('home')

    form = LandlordRoomForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        landlord=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        room = form.save()
        messages.success(request, f'{room.get_room_type_display()} has been added.')
        return redirect('landlord_dashboard')

    return render(request, 'accounts/landlord_form.html', {
        'form': form,
        'page_title': 'Add a room',
        'page_description': 'Choose one of your properties and add its room details.',
        'submit_label': 'Save room',
        'has_properties': House.objects.filter(landlord=request.user).exists(),
    })


@login_required
def account_settings(request):
    # Tumia profile ya mtumiaji aliyeingia pekee kwa mipangilio yake binafsi.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    section = request.POST.get(
        'section',
        request.GET.get('section', 'profile_picture'),
    )
    if section not in {'account_options', 'profile_picture', 'change_password', 'student_details'}:
        return redirect('account_settings')

    student_details_form = StudentDetailsForm(
        request.POST if request.method == 'POST' and section == 'student_details' else None,
        user=request.user,
        profile=profile,
    )
    if request.method == 'POST' and section == 'student_details':
        if student_details_form.is_valid():
            student_details_form.save()
            messages.success(request, 'Student details updated successfully.')
            return redirect(_account_return_url(request, profile))

    return render(request, 'accounts/account_settings.html', {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
        'student_details_form': student_details_form,
        'password_form': LandlordPasswordChangeForm(user=request.user),
        'section': section,
        'return_url': _account_return_url(request, profile),
    })


def _account_return_url(request, profile):
    candidate = (
        request.POST.get('next')
        or request.GET.get('next')
        or request.META.get('HTTP_REFERER')
    )
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    if profile.user_type == 'landlord':
        return reverse('landlord_dashboard')
    return reverse('house_list')


@login_required
def update_profile_pic(request):
    # Fomu inaunganishwa na profile ya session ya sasa, si profile iliyotumwa na browser.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return_url = _account_return_url(request, profile)

    if request.method == 'POST':
        form = ProfilePicForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile picture updated successfully.')
        else:
            messages.error(request, 'Please choose a valid image file.')

    return redirect(return_url)


@login_required
def save_house(request, pk):
    # Kitufe kimoja huongeza au kuondoa nyumba kwenye orodha ya mwanafunzi.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'student':
        messages.error(request, 'Only students can save properties.')
        return redirect('landlord_dashboard')
    if request.method != 'POST':
        return redirect('house_detail', pk=pk)

    house = get_object_or_404(House, pk=pk)
    saved_house = SavedHouse.objects.filter(
        student=request.user,
        house=house,
    ).first()
    if saved_house:
        saved_house.delete()
        messages.info(request, f'"{house.title}" was removed from your saved homes.')
    elif house.is_available:
        SavedHouse.objects.create(student=request.user, house=house)
        messages.success(request, f'"{house.title}" was added to your saved homes.')
    else:
        messages.error(request, 'This property is no longer available to save.')
    return redirect(_account_return_url(request, profile))


@login_required
def apply_for_room(request, pk):
    # Mwanafunzi anatuma ombi moja hai kwa chumba na mwenye nyumba anapokea taarifa.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'student':
        messages.error(request, 'Only students can request a room booking.')
        return redirect('landlord_dashboard')
    room = get_object_or_404(
        Room.objects.select_related('house', 'house__landlord'),
        pk=pk,
        house__is_available=True,
    )
    if request.method != 'POST':
        return redirect('house_detail', pk=room.house_id)

    form = BookingMessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please enter a valid message for the landlord.')
        return redirect('house_detail', pk=room.house_id)

    try:
        with transaction.atomic():
            # Lock room hii ili request na approval zisikague availability kwa wakati mmoja.
            room = Room.objects.select_for_update().select_related(
                'house',
                'house__landlord',
            ).get(pk=pk)
            if not room.house.is_available:
                messages.error(request, 'This property is no longer available.')
                return redirect('house_detail', pk=room.house_id)
            if Booking.objects.filter(
                room=room,
                status=Booking.STATUS_APPROVED,
            ).exists():
                messages.error(request, 'This room has already been booked.')
                return redirect('house_detail', pk=room.house_id)
            existing_booking = Booking.objects.filter(
                student=request.user,
                room=room,
                status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
            ).exists()
            if existing_booking:
                messages.info(request, 'You already have an active request for this room.')
                return redirect('student_dashboard')
            booking = Booking.objects.create(
                student=request.user,
                room=room,
                student_message=form.cleaned_data['message'].strip(),
            )
    except IntegrityError:
        if Booking.objects.filter(
            room=room,
            status=Booking.STATUS_APPROVED,
        ).exists():
            messages.error(request, 'This room has already been booked.')
            return redirect('house_detail', pk=room.house_id)
        messages.info(request, 'You already have an active request for this room.')
        return redirect('student_dashboard')
    StudentNotification.objects.create(
        recipient=room.house.landlord,
        booking=booking,
        notification_type=StudentNotification.TYPE_BOOKING,
        title='New room booking request',
        message=f'{request.user.get_full_name() or request.user.username} requested {room.get_room_type_display()} at {room.house.title}.',
    )
    messages.success(request, 'Your booking request was sent to the landlord.')
    return redirect('student_dashboard')


@login_required
def initiate_booking_payment_view(request, pk):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'student':
        messages.error(request, 'Only students can pay for an approved room booking.')
        return redirect('landlord_dashboard')
    if request.method != 'POST':
        return redirect('student_dashboard')

    booking = get_object_or_404(
        Booking.objects.select_related('room'),
        pk=pk,
        student=request.user,
    )
    return_url = f'{reverse("house_detail", args=[booking.room.house_id])}#room-{booking.room_id}'
    form = BookingPaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors['phone_number'][0])
        return redirect(return_url)

    try:
        order_reference = initiate_booking_payment(
            booking_id=booking.pk,
            student=request.user,
            phone_number=form.cleaned_data['phone_number'],
        )
    except BookingPaymentError as error:
        if error.request_may_have_been_sent:
            messages.warning(request, str(error))
        else:
            messages.error(request, str(error))
        return redirect(return_url)

    StudentNotification.objects.create(
        recipient=request.user,
        booking=booking,
        notification_type=StudentNotification.TYPE_PAYMENT,
        title='USSD payment request sent',
        message=(
            f'A USSD request for TZS {booking.room.price} was sent to '
            f'{form.cleaned_data["phone_number"]}. Reference: {order_reference}. '
            'Payment remains pending until the landlord confirms receipt.'
        ),
    )
    messages.success(
        request,
        'USSD payment request sent. Enter your mobile money PIN on your phone. '
        'Your booking will remain pending until the landlord confirms receipt.',
    )
    return redirect(return_url)


@login_required
def landlord_update_booking(request, pk):
    # Ruhusu mwenye nyumba husika pekee kusimamia maombi na mawasiliano ya booking.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'landlord':
        messages.error(request, 'This action is available to landlords only.')
        return redirect('student_dashboard')
    if request.method != 'POST':
        return redirect('landlord_dashboard')

    booking = get_object_or_404(
        Booking.objects.select_related('student', 'room', 'room__house'),
        pk=pk,
        room__house__landlord=request.user,
    )
    action = request.POST.get('action')

    if action in {'approve', 'reject'}:
        if booking.status != Booking.STATUS_PENDING:
            messages.error(request, 'Only pending booking requests can be reviewed.')
            return redirect('landlord_dashboard')
        if action == 'approve':
            try:
                with transaction.atomic():
                    # Approval na request mpya zinashindana kwa lock hiyo hiyo ya room.
                    Room.objects.select_for_update().get(pk=booking.room_id)
                    booking.refresh_from_db()
                    if not booking.room.house.is_available:
                        messages.error(request, 'This property is no longer available.')
                        return redirect('landlord_dashboard')
                    another_approved_booking = Booking.objects.filter(
                        room=booking.room,
                        status=Booking.STATUS_APPROVED,
                    ).exclude(pk=booking.pk).exists()
                    if another_approved_booking:
                        messages.error(request, 'This room already has an approved booking.')
                        return redirect('landlord_dashboard')
                    booking.status = Booking.STATUS_APPROVED
                    booking.save(update_fields=['status', 'updated_at'])
                    title = 'Booking request approved'
                    body = f'Your request for {booking.room.get_room_type_display()} at {booking.room.house.title} was approved.'
            except IntegrityError:
                messages.error(request, 'This room already has an approved booking.')
                return redirect('landlord_dashboard')
        else:
            booking.status = Booking.STATUS_REJECTED
            title = 'Booking request declined'
            body = f'Your request for {booking.room.get_room_type_display()} at {booking.room.house.title} was declined.'
            booking.save(update_fields=['status', 'updated_at'])
        StudentNotification.objects.create(
            recipient=booking.student,
            booking=booking,
            notification_type=StudentNotification.TYPE_BOOKING,
            title=title,
            message=body,
        )
        messages.success(request, 'Booking request updated.')
    elif action == 'message':
        form = BookingMessageForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Please enter a message before sending.')
            return redirect('landlord_dashboard')
        message = form.cleaned_data['message'].strip()
        BookingMessage.objects.create(
            booking=booking,
            sender=request.user,
            message=message,
        )
        StudentNotification.objects.create(
            recipient=booking.student,
            booking=booking,
            notification_type=StudentNotification.TYPE_MESSAGE,
            title='New message from your landlord',
            message=message,
        )
        messages.success(request, 'Your message was sent to the student.')
    elif action == 'payment_reminder':
        if booking.status != Booking.STATUS_APPROVED:
            messages.error(request, 'Payment reminders are available for approved bookings.')
            return redirect('landlord_dashboard')
        StudentNotification.objects.create(
            recipient=booking.student,
            booking=booking,
            notification_type=StudentNotification.TYPE_PAYMENT,
            title='Payment reminder',
            message=f'Please contact your landlord about payment for {booking.room.house.title}. Payment is recorded as unpaid until confirmed.',
        )
        messages.success(request, 'Payment reminder sent.')
    elif action == 'confirm_payment':
        if booking.status != Booking.STATUS_APPROVED:
            messages.error(request, 'Only approved bookings can have payment confirmed.')
            return redirect('landlord_dashboard')
        booking.payment_status = Booking.PAYMENT_PAID
        booking.save(update_fields=['payment_status', 'updated_at'])
        StudentNotification.objects.create(
            recipient=booking.student,
            booking=booking,
            notification_type=StudentNotification.TYPE_PAYMENT,
            title='Payment confirmed',
            message=f'Your landlord confirmed payment for {booking.room.house.title}.',
        )
        messages.success(request, 'Payment was marked as received based on your confirmation.')
    else:
        messages.error(request, 'Unknown booking action.')

    return redirect('landlord_dashboard')


@login_required
def send_booking_message(request, pk):
    if request.method != 'POST':
        return redirect('student_dashboard')

    # Ujumbe unaruhusiwa tu kwa booking inayosubiri/iliyoidhinishwa na wahusika wake.
    booking = get_object_or_404(
        Booking.objects.filter(
            status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
        ).select_related('student', 'room', 'room__house', 'room__house__landlord'),
        Q(student=request.user) | Q(room__house__landlord=request.user),
        pk=pk,
    )
    form = BookingMessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please enter a message before sending.')
        return _booking_dashboard_redirect(request.user)

    BookingMessage.objects.create(
        booking=booking,
        sender=request.user,
        message=form.cleaned_data['message'].strip(),
    )
    # Arifa inaenda kwa mshiriki mwingine wa mazungumzo, si mtumaji.
    is_landlord = request.user.pk == booking.room.house.landlord_id
    recipient = booking.student if is_landlord else booking.room.house.landlord
    StudentNotification.objects.create(
        recipient=recipient,
        booking=booking,
        notification_type=(
            StudentNotification.TYPE_MESSAGE
            if is_landlord else StudentNotification.TYPE_STUDENT_MESSAGE
        ),
        title='New message from landlord' if is_landlord else 'New message from student',
        message=form.cleaned_data['message'].strip(),
    )
    messages.success(request, 'Your message was sent.')
    return _booking_dashboard_redirect(request.user)


def _booking_dashboard_redirect(user):
    if user.user_type == 'landlord':
        return redirect('landlord_dashboard')
    return redirect('student_dashboard')


@login_required
def submit_booking_review(request, pk):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'student':
        messages.error(request, 'Only students can review a booking.')
        return redirect('landlord_dashboard')
    if request.method != 'POST':
        return redirect('student_dashboard')

    booking = get_object_or_404(Booking, pk=pk, student=request.user)
    # Review inawezekana baada tu ya booking kuidhinishwa na malipo kuthibitishwa.
    if booking.status != Booking.STATUS_APPROVED or booking.payment_status != Booking.PAYMENT_PAID:
        messages.error(request, 'You can review a booking after it is approved and paid.')
        return redirect('student_dashboard')
    if Review.objects.filter(booking=booking).exists():
        messages.info(request, 'You have already reviewed this booking.')
        return redirect('student_dashboard')

    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.booking = booking
        try:
            with transaction.atomic():
                review.save()
        except IntegrityError:
            messages.info(request, 'You have already reviewed this booking.')
        else:
            messages.success(request, 'Thank you for sharing your review.')
    else:
        messages.error(request, 'Please choose a valid rating and try again.')
    return redirect('student_dashboard')


@login_required
def report_house(request, pk):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    house = get_object_or_404(House, pk=pk)
    if profile.user_type != 'student' or house.landlord_id == request.user.pk:
        messages.error(request, 'Only students can report another landlord’s listing.')
        return redirect('house_detail', pk=house.pk)
    if request.method != 'POST':
        return redirect('house_detail', pk=house.pk)

    # Mwanafunzi anaweza kuwa na ripoti moja inayosubiri kwa nyumba; admin akimaliza, anaweza kuripoti tena.
    form = HouseReportForm(request.POST)
    if form.is_valid():
        existing_report = HouseReport.objects.filter(
            house=house,
            reporter=request.user,
            status=HouseReport.STATUS_PENDING,
        ).first()
        if existing_report:
            messages.info(request, 'You already have a report awaiting review for this listing.')
        else:
            report = form.save(commit=False)
            report.house = house
            report.reporter = request.user
            try:
                # Atomic hulinda dhidi ya maombi mawili yanayowasilishwa kwa wakati mmoja.
                with transaction.atomic():
                    report.save()
            except IntegrityError:
                messages.info(request, 'You already have a report awaiting review for this listing.')
            else:
                messages.success(request, 'Your report was sent to the review team.')
    else:
        messages.error(request, 'Please choose a reason for reporting this listing.')
    return redirect('house_detail', pk=house.pk)


@login_required
def mark_notification_read(request, pk):
    # Mmiliki wa notification pekee ndiye anayeruhusiwa kuisoma au kuifunga.
    if request.method == 'POST':
        notification = get_object_or_404(
            StudentNotification,
            pk=pk,
            recipient=request.user,
        )
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return _booking_dashboard_redirect(request.user)


@login_required
def submit_support_request(request):
    # Hifadhi ombi la msaada kwenye akaunti ya mwanafunzi aliyeingia.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'student':
        messages.error(request, 'This support form is available to students only.')
        return redirect('landlord_dashboard')
    if request.method == 'POST':
        form = SupportRequestForm(request.POST)
        if form.is_valid():
            form.save(student=request.user)
            messages.success(request, 'Your support request was submitted.')
        else:
            messages.error(request, 'Please enter a valid support request.')
    return redirect('student_dashboard')


@login_required
def landlord_delete_house(request, pk):
    profile = _ensure_landlord(request)
    if profile is None:
        return redirect('home')

    house = get_object_or_404(House, pk=pk, landlord=request.user)
    if request.method == 'POST':
        title = house.title
        house.delete()
        messages.success(request, f'"{title}" has been deleted.')

    return redirect('landlord_dashboard')


@login_required
def landlord_change_password(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return_url = _account_return_url(request, profile)

    if request.method != 'POST':
        return redirect(return_url)

    password_form = LandlordPasswordChangeForm(user=request.user, data=request.POST)
    if password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        messages.success(
            request,
            'Password changed successfully. Use the new password next time you sign in.',
        )
        return redirect(return_url)

    if profile.user_type != 'landlord':
        return render(request, 'accounts/account_settings.html', {
            'profile': profile,
            'profile_form': ProfilePicForm(instance=profile),
            'password_form': password_form,
            'section': 'change_password',
            'return_url': return_url,
        })

    houses = (
        House.objects.filter(landlord=request.user)
        .prefetch_related('rooms')
        .order_by('-created_at')
    )
    rooms = Room.objects.filter(house__landlord=request.user)
    landlord_bookings = Booking.objects.filter(
        room__house__landlord=request.user,
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
    ).select_related('student', 'student__profile', 'room', 'room__house').prefetch_related('messages__sender')
    notifications = StudentNotification.objects.filter(recipient=request.user)
    unread_message_count = notifications.filter(
        is_read=False,
        notification_type__in=[
            StudentNotification.TYPE_MESSAGE,
            StudentNotification.TYPE_STUDENT_MESSAGE,
        ],
    ).count()
    context = {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
        'password_form': password_form,
        'houses': houses[:10],
        'total_properties': houses.count(),
        'available_property_rooms': rooms.filter(house__is_available=True).count(),
        'unavailable_property_rooms': rooms.filter(house__is_available=False).count(),
        'open_password_modal': True,
        'pending_bookings': landlord_bookings.filter(status=Booking.STATUS_PENDING)[:20],
        'landlord_bookings': landlord_bookings[:50],
        'pending_booking_count': landlord_bookings.filter(status=Booking.STATUS_PENDING).count(),
        'unread_message_count': unread_message_count,
        'pending_payment_confirmation_count': landlord_bookings.filter(
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_PENDING,
        ).count(),
        'notifications': notifications[:8],
        'unread_notification_count': notifications.filter(is_read=False).count(),
    }
    return render(request, 'accounts/landlord_dashboard.html', context)
