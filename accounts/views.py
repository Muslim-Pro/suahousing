import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.db import IntegrityError, transaction
from django.db.models import Count, Min
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.template.loader import render_to_string

from houses.models import House, Room

from .forms import (
    CustomPasswordResetForm,
    BookingMessageForm,
    LandlordHouseForm,
    LandlordPasswordChangeForm,
    LandlordRoomForm,
    ProfilePicForm,
    StudentDetailsForm,
    SupportRequestForm,
    UserRegisterForm,
)
from .models import (
    Booking,
    BookingMessage,
    Profile,
    SavedHouse,
    StudentNotification,
    SupportRequest,
)
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
    ).select_related('student', 'student__profile', 'room', 'room__house')

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
    }
    return render(request, 'accounts/landlord_dashboard.html', context)


@login_required
def student_dashboard(request):
    # Kusanya listings, bookings, saved homes na taarifa kwa mwanafunzi huyu pekee.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type == 'landlord':
        return redirect('landlord_dashboard')

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
        .prefetch_related('messages')
    )
    booking_list = list(bookings[:10])
    for booking in booking_list:
        landlord_phone = booking.room.house.landlord.profile.phone
        booking.landlord_whatsapp = tanzania_whatsapp_number(landlord_phone)
    saved_houses = SavedHouse.objects.filter(
        student=request.user,
    ).select_related('house')
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
    }
    return render(request, 'accounts/student_dashboard.html', context)


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

    existing_booking = Booking.objects.filter(
        student=request.user,
        room=room,
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
    ).first()
    if existing_booking:
        messages.info(request, 'You already have an active request for this room.')
        return redirect('student_dashboard')

    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                student=request.user,
                room=room,
                student_message=form.cleaned_data['message'].strip(),
            )
    except IntegrityError:
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
            with transaction.atomic():
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
    return redirect('student_dashboard')


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
    ).select_related('student', 'student__profile', 'room', 'room__house')
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
    }
    return render(request, 'accounts/landlord_dashboard.html', context)
