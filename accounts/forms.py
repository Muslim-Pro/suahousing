import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import Profile


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


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
