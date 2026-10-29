from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q

from houses.models import House, Room


class Profile(models.Model):
    YEAR_OF_STUDY_CHOICES = [
        (f'Year {year}', f'Year {year}')
        for year in range(1, 6)
    ]
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
    university = models.CharField(max_length=150, blank=True)
    year_of_study = models.CharField(
        max_length=50,
        choices=YEAR_OF_STUDY_CHOICES,
        blank=True,
    )
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_user_type_display()})'


class SavedHouse(models.Model):
    # Hifadhi nyumba anazopenda mwanafunzi bila kurudia rekodi moja.
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='saved_houses',
    )
    house = models.ForeignKey(
        House,
        on_delete=models.CASCADE,
        related_name='saved_by_students',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'house'],
                name='unique_saved_house_per_student',
            ),
        ]

    def __str__(self):
        return f'{self.student.username} saved {self.house.title}'


class Booking(models.Model):
    # Omba chumba; mwenye nyumba ndiye anayekubali au kukataa ombi.
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    PAYMENT_UNPAID = 'unpaid'
    PAYMENT_PENDING = 'pending'
    PAYMENT_PAID = 'paid'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_UNPAID, 'Unpaid'),
        (PAYMENT_PENDING, 'Pending verification'),
        (PAYMENT_PAID, 'Paid'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='room_bookings',
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='booking_requests',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_UNPAID,
    )
    payment_reference = models.CharField(max_length=32, blank=True)
    payment_phone_number = models.CharField(max_length=12, blank=True)
    receipt_verification_token = models.UUIDField(
        blank=True,
        null=True,
        unique=True,
        editable=False,
    )
    student_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'room'],
                condition=Q(status__in=['pending', 'approved']),
                name='unique_active_booking_per_student_room',
            ),
        ]

    def __str__(self):
        return f'{self.student.username} - {self.room}'


class BookingMessage(models.Model):
    # Rekodi mawasiliano ya mwanafunzi na mwenye nyumba kuhusu booking.
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='booking_messages',
    )
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Message for booking {self.booking_id} from {self.sender.username}'


class StudentNotification(models.Model):
    # Hifadhi ujumbe, vikumbusho na mabadiliko ya booking kwa mpokeaji.
    TYPE_BOOKING = 'booking_update'
    TYPE_MESSAGE = 'landlord_message'
    TYPE_PAYMENT = 'payment_reminder'
    TYPE_CHOICES = [
        (TYPE_BOOKING, 'Booking update'),
        (TYPE_MESSAGE, 'Landlord message'),
        (TYPE_PAYMENT, 'Payment reminder'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='student_notifications',
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=160)
    message = models.TextField(max_length=1000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} for {self.recipient.username}'


class SupportRequest(models.Model):
    # Fuatilia maombi ya msaada ya mwanafunzi kutoka kwenye dashboard.
    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_CLOSED, 'Closed'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='support_requests',
    )
    message = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Support request from {self.student.username}'
