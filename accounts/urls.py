from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path(
        'landlord/dashboard/',
        RedirectView.as_view(pattern_name='landlord_dashboard', permanent=False),
    ),
    path('landlord/profile-pic/', views.update_profile_pic, name='update_profile_pic'),
    path('landlord/change-password/', views.landlord_change_password, name='landlord_change_password'),
    path(
        'landlord/houses/<int:pk>/delete/',
        views.landlord_delete_house,
        name='landlord_delete_house',
    ),
]