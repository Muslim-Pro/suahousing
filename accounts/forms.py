import logging
import re
from smtplib import SMTPException

from django import forms
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from houses.models import House, Room

from .models import Profile


logger = logging.getLogger(__name__)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class CustomPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'email',
        })

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = ''.join(
            render_to_string(subject_template_name, context).splitlines()
        ).strip()
        body = render_to_string(email_template_name, context)
        email_message = EmailMultiAlternatives(
            subject,
            body,
            from_email,
            [to_email],
        )
        if html_email_template_name:
            html_email = render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, 'text/html')

        try:
            if not email_message.send():
                logger.error('Password reset email was not accepted by the email backend.')
        except (OSError, SMTPException):
            logger.exception('Failed to deliver a password reset email.')


class UserRegisterForm(UserCreationForm):
    username = forms.CharField(
        required=True,
        label="Username",
        widget=forms.TextInput(attrs={
            'class': 'form-control py-2',
            'placeholder': 'Enter username',
            'autocomplete': 'username',
        })
    )
    first_name = forms.CharField(
        required=True,
        label="First Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control py-2',
            'placeholder': 'Enter first name',
            'autocomplete': 'given-name',
        })
    )
    last_name = forms.CharField(
        required=True,
        label="Last Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control py-2',
            'placeholder': 'Enter last name',
            'autocomplete': 'family-name',
        })
    )
    email = forms.EmailField(
        required=True,
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control py-2',
            'placeholder': 'example@gmail.com',
            'autocomplete': 'email',
            'id': 'id_email',
        })
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'password1' in self.fields:
            self.fields['password1'].widget = forms.PasswordInput(attrs={
                'class': 'form-control py-2',
                'placeholder': 'Enter password',
                'autocomplete': 'new-password',
            })
            self.fields['password1'].label = "Password"
        if 'password2' in self.fields:
            self.fields['password2'].widget = forms.PasswordInput(attrs={
                'class': 'form-control py-2',
                'placeholder': 'Confirm password',
                'autocomplete': 'new-password',
            })
            self.fields['password2'].label = "Password confirmation"

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()

        if not email:
            raise ValidationError('Email address is required.')

        if not EMAIL_REGEX.match(email):
            raise ValidationError('Please enter a valid email address (e.g. name@gmail.com).')

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('This email is already registered. Please sign in or use another email.')

        return email


class ProfilePicForm(forms.ModelForm):
    profile_pic = forms.ImageField(
        required=True,
        label='Profile picture',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
        }),
    )

    class Meta:
        model = Profile
        fields = ['profile_pic']


class LandlordPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Current password',
            'autocomplete': 'current-password',
        })
        self.fields['old_password'].label = 'Current password'
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'New password',
            'autocomplete': 'new-password',
        })
        self.fields['new_password1'].label = 'New password'
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
        self.fields['new_password2'].label = 'Confirm new password'


class LandlordHouseForm(forms.ModelForm):
    class Meta:
        model = House
        fields = ['title', 'description', 'location', 'address', 'image']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Green View Hostel',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the property and its facilities',
            }),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street, landmark or nearby campus',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }


# Bei ya chumba inakubali namba chanya pekee, na orodha ya nyumba huchujwa
# kulingana na mwenye akaunti ili landlord asiongeze chumba kwenye nyumba ya mtu mwingine.
class LandlordRoomForm(forms.ModelForm):
    price = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'placeholder': 'Price in TZS',
        }),
    )

    class Meta:
        model = Room
        fields = ['house', 'room_type', 'price', 'room_image', 'description']
        widgets = {
            'house': forms.Select(attrs={'class': 'form-select'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'room_image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional details about the room',
            }),
        }

    def __init__(self, *args, landlord, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['house'].queryset = House.objects.filter(
            landlord=landlord,
        ).order_by('title')
