from django.contrib import admin
from django.db import transaction
from django.utils import timezone

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


@admin.register(LandlordApplication)
class LandlordApplicationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'property_address', 'applicant_type', 'status', 'submitted_at')
    list_filter = ('status', 'applicant_type', 'submitted_at')
    search_fields = ('profile__user__username', 'profile__user__email', 'profile__phone', 'property_address')
    readonly_fields = ('profile', 'property_address', 'applicant_type', 'verification_details', 'submitted_at', 'reviewed_at', 'reviewed_by')
    fields = (
        'profile',
        'property_address',
        'applicant_type',
        'verification_details',
        'status',
        'admin_note',
        'submitted_at',
        'reviewed_at',
        'reviewed_by',
    )

    def save_model(self, request, obj, form, change):
        if 'status' in form.changed_data:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()

        # Hifadhi uamuzi na role pamoja ili approval isiache akaunti kwenye hali isiyolingana.
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            profile = obj.profile
            user_type = (
                Profile.TYPE_LANDLORD
                if obj.status == LandlordApplication.STATUS_APPROVED
                else Profile.TYPE_STUDENT
            )
            if profile.user_type != user_type:
                profile.user_type = user_type
                profile.save(update_fields=['user_type'])


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('student', 'room', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status')
    search_fields = ('student__username', 'student__email', 'room__house__title')


@admin.register(SavedHouse)
class SavedHouseAdmin(admin.ModelAdmin):
    list_display = ('student', 'house', 'created_at')
    search_fields = ('student__username', 'house__title')


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ('student', 'location', 'room_type', 'minimum_price', 'maximum_price', 'created_at')
    list_filter = ('location', 'room_type', 'created_at')
    search_fields = ('student__username', 'student__email')


@admin.register(BookingMessage)
class BookingMessageAdmin(admin.ModelAdmin):
    list_display = ('booking', 'sender', 'created_at')
    search_fields = ('sender__username', 'message', 'booking__student__username')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('booking', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('booking__student__username', 'booking__room__house__title', 'comment')


@admin.register(HouseReport)
class HouseReportAdmin(admin.ModelAdmin):
    list_display = ('house', 'reporter', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('house__title', 'reporter__username', 'details')
    readonly_fields = ('house', 'reporter', 'reason', 'details', 'created_at')


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
