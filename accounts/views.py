import random
import re
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from .forms import UserRegisterForm


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
