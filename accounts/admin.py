from django.contrib import admin

from .models import (
    Booking,
    BookingMessage,
    Profile,
    SavedHouse,
    StudentNotification,
    SupportRequest,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'user_type',
        'phone',
        'university',
        'year_of_study',
        'emergency_contact_name',
        'emergency_contact_phone',
    )
    list_filter = ('user_type',)
    search_fields = (
        'user__username',
        'user__email',
        'phone',
        'university',
        'emergency_contact_name',
        'emergency_contact_phone',
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('student', 'room', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status')
    search_fields = ('student__username', 'student__email', 'room__house__title')


@admin.register(SavedHouse)
class SavedHouseAdmin(admin.ModelAdmin):
    list_display = ('student', 'house', 'created_at')
    search_fields = ('student__username', 'house__title')


@admin.register(BookingMessage)
class BookingMessageAdmin(admin.ModelAdmin):
    list_display = ('booking', 'sender', 'created_at')
    search_fields = ('sender__username', 'message', 'booking__student__username')


@admin.register(StudentNotification)
class StudentNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('recipient__username', 'title', 'message')


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'student__email', 'message')
