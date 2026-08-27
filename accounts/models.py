from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    USER_TYPES = [
        ('student', 'Student'),
        ('landlord', 'Landlord'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='student')
    profile_pic = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        verbose_name='Profile picture',
    )
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_user_type_display()})'
