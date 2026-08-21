from django.urls import path
from . import views

urlpatterns = [
    # url nyingine, login na register zilizopo hapa
    path('forgot-password/', views.forgot_password, name='forgot_password'),
]