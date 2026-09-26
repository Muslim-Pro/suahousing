from django.urls import path
from . import views

urlpatterns = [
   
    path('anzisha-malipo/<int:house_id>/', views.anzisha_malipo, name='anzisha_malipo'),
    path('house/<int:house_id>/pay/', views.initiate_flutterwave_payment, name='initiate_flutterwave_payment'),
]
