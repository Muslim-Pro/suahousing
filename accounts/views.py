import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.template.loader import render_to_string

from houses.models import House, Room

from .forms import (
    CustomPasswordResetForm,
    LandlordHouseForm,
    LandlordPasswordChangeForm,
    LandlordRoomForm,
    ProfilePicForm,
    UserRegisterForm,
)
from .models import Profile


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
    """Baada ya login, landlord anaenda dashboard; student anaenda houses."""

    def form_valid(self, form):
        response = super().form_valid(form)
        jina = self.request.user.get_full_name() or self.request.user.username
        messages.success(self.request, f'Welcome back, {jina}!')
        return response

    def get_success_url(self):
        next_url = self.get_redirect_url()
        if next_url:
            return next_url
        try:
            if self.request.user.profile.user_type == 'landlord':
                return reverse('landlord_dashboard')
        except Exception:
            pass
        return reverse('house_list')


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

    context = {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
        'password_form': LandlordPasswordChangeForm(user=request.user),
        'houses': houses[:10],
        'total_properties': houses.count(),
        'available_property_rooms': rooms.filter(house__is_available=True).count(),
        'unavailable_property_rooms': rooms.filter(house__is_available=False).count(),
        'open_password_modal': False,
    }
    return render(request, 'accounts/landlord_dashboard.html', context)


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
    section = request.GET.get('section', 'profile_picture')
    if section not in {'profile_picture', 'change_password'}:
        return redirect('account_settings')

    return render(request, 'accounts/account_settings.html', {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
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
    context = {
        'profile': profile,
        'profile_form': ProfilePicForm(instance=profile),
        'password_form': password_form,
        'houses': houses[:10],
        'total_properties': houses.count(),
        'available_property_rooms': rooms.filter(house__is_available=True).count(),
        'unavailable_property_rooms': rooms.filter(house__is_available=False).count(),
        'open_password_modal': True,
    }
    return render(request, 'accounts/landlord_dashboard.html', context)
