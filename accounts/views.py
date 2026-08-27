import random
import re
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.template.loader import render_to_string

from houses.models import House, Room

from .forms import LandlordPasswordChangeForm, ProfilePicForm, UserRegisterForm
from .models import Profile


def forgot_password(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')

        if not username or not email:
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all fields!'
            })

        try:
            user = User.objects.get(username=username, email=email)

            characters = string.ascii_letters + string.digits
            new_password = ''.join(random.choice(characters) for _ in range(8))

            user.set_password(new_password)
            user.save()

            subject = 'Your New Password - SUA Student Housing'
            recipient_list = [email]
            context = {
                'username': user.username,
                'first_name': user.first_name or user.username,
                'new_password': new_password,
                'login_url': request.build_absolute_uri('/accounts/login/'),
                'support_email': settings.SUPPORT_EMAIL,
            }

            html_content = render_to_string('emails/new_password.html', context)
            text_content = (
                f"Hello {context['first_name']},\n"
                f"Your new password is: {new_password}\n"
                f"Login: {context['login_url']}"
            )

            msg = EmailMultiAlternatives(
                subject, text_content, settings.DEFAULT_FROM_EMAIL, recipient_list
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send()

            return JsonResponse({
                'success': True,
                'message': 'A new password has been sent to your email address!'
            })

        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'No user found with that username and email combination.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


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

            try:
                msg = EmailMultiAlternatives(
                    subject, text_content, settings.DEFAULT_FROM_EMAIL, [email]
                )
                msg.attach_alternative(html_content, 'text/html')
                msg.send()
                messages.success(
                    request,
                    f'Welcome {first_name}! Your account has been created successfully. Check your email (inbox/spam) for login information.'
                )
            except Exception:
                messages.success(
                    request,
                    f'Welcome {first_name}! Your account has been created successfully. You can log in now.'
                )

            # return redirect('login')

        # messages.error(request, 'Please correct the errors in the form before proceeding.')
    else:
        form = UserRegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


class CustomLoginView(LoginView):
    """Baada ya login, landlord anaenda dashboard; student anaenda houses."""

    def form_valid(self, form):
        response = super().form_valid(form)
        jina = self.request.user.first_name or self.request.user.username
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


def _redirect_back(request):
    """Rudisha mtumiaji kwenye ukurasa alikotoka baada ya kubadilisha picha au password."""
    candidate = request.META.get('HTTP_REFERER', '')
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return redirect(candidate)
    try:
        if request.user.profile.user_type == 'landlord':
            return redirect('landlord_dashboard')
    except Exception:
        pass
    return redirect('house_list')


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
        'vacant_rooms': rooms.filter(house__is_available=True).count(),
        'occupied_rooms': rooms.filter(house__is_available=False).count(),
        'total_inquiries': 0,
        'open_password_modal': False,
    }
    return render(request, 'accounts/landlord_dashboard.html', context)


@login_required
def update_profile_pic(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProfilePicForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile picture updated successfully.')
        else:
            messages.error(request, 'Please choose a valid image file.')

    return _redirect_back(request)


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
    if request.method != 'POST':
        return _redirect_back(request)

    password_form = LandlordPasswordChangeForm(user=request.user, data=request.POST)
    if password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        messages.success(
            request,
            'Password changed successfully. Use the new password next time you sign in.',
        )
        return _redirect_back(request)

    for field_errors in password_form.errors.values():
        messages.error(request, field_errors[0])
        break
    return _redirect_back(request)
