from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path(
        'receipts/verify/<uuid:token>/',
        views.verify_payment_receipt,
        name='verify_payment_receipt',
    ),
    path(
        'forgot-password/',
        views.CustomPasswordResetView.as_view(),
        name='forgot_password',
    ),
    path(
        'landlord/dashboard/',
        RedirectView.as_view(pattern_name='landlord_dashboard', permanent=False),
    ),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/houses/<int:pk>/save/', views.save_house, name='save_house'),
    path('student/rooms/<int:pk>/book/', views.apply_for_room, name='apply_for_room'),
    path(
        'student/bookings/<int:pk>/pay/',
        views.initiate_booking_payment_view,
        name='initiate_booking_payment',
    ),
    path(
        'student/bookings/<int:pk>/receipt/',
        views.booking_payment_receipt,
        name='booking_payment_receipt',
    ),
    path('student/notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('student/support/', views.submit_support_request, name='submit_support_request'),
    path('landlord/bookings/<int:pk>/', views.landlord_update_booking, name='landlord_update_booking'),
    path('settings/', views.account_settings, name='account_settings'),
    path('profile-picture/', views.update_profile_pic, name='account_profile_picture'),
    path('change-password/', views.landlord_change_password, name='account_change_password'),
    # Fomu hizi zinatumia owner check kwenye view na queryset ya landlord kwenye form.
    path('landlord/properties/add/', views.landlord_add_property, name='landlord_add_property'),
    path('landlord/rooms/add/', views.landlord_add_room, name='landlord_add_room'),
    path('landlord/profile-pic/', views.update_profile_pic, name='update_profile_pic'),
    # Njia ya zamani ya landlord inabaki kwa links zilizokwisha tumika.
    path('landlord/change-password/', views.landlord_change_password, name='landlord_change_password'),
    path(
        'landlord/houses/<int:pk>/delete/',
        views.landlord_delete_house,
        name='landlord_delete_house',
    ),
]