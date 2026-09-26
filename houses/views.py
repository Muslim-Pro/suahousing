# from django.shortcuts import render

# Create your views here.


from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Min
from django.contrib.auth.models import User
from .models import House, Room
from django.contrib.auth.decorators import login_required
# kuhusu flutterwave, tutaongeza views.py hapa chini ili kuanzisha malipo na kudhibiti matokeo ya maplipo 
import uuid
import requests
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from .models import House  # Hakikisha model yako ya House imekuwa imported


def anzisha_malipo(request, house_id):
    house = get_object_or_404(House, id=house_id)
    
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')  # Mfano: 0712345678
        amount = request.POST.get('amount')
        network = request.POST.get('network')  # MPS (M-Pesa), TIGO, au AIRTEL

        # Formatting namba ya simu
        if phone_number.startswith('+255'):
            phone_number = '0' + phone_number[4:]
        elif phone_number.startswith('255'):
            phone_number = '0' + phone_number[3:]

        # Tengeneza Unique Reference
        tx_ref = f"SUA-HOUSE-{uuid.uuid4().hex[:8].upper()}"

        # Payload ya Flutterwave Tanzania Mobile Money
        payload = {
            "tx_ref": tx_ref,
            "amount": amount,
            "currency": "TZS",
            "email": request.user.email if request.user.is_authenticated else "mteja@example.com",
            "phone_number": phone_number,
            "network": network,  # 'MPS', 'TIGO', au 'AIRTEL'
            "type": "mobile_money_tanzania"
        }

        headers = {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        try:
            url = "https://api.flutterwave.com/v3/charges?type=mobile_money_tanzania"
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            res_data = response.json()

            if response.status_code == 200 and res_data.get('status') == 'success':
                messages.success(
                    request, 
                    f"Ombi la TZS {amount} limetumwa kwenda {phone_number} ({network}). Angalia simu yako kuweka PIN!"
                )
            else:
                msg = res_data.get('message', 'Imeshindikana kutuma ombi la malipo.')
                messages.error(request, f"Makosa: {msg}")

        except Exception as e:
            messages.error(request, f"Hitilafu ya mtandao: {str(e)}")

        return redirect('house_detail', pk=house_id)

    return redirect('house_detail', pk=house_id)




def home(request):
    """Ukurasa wa kukaribisha — unaweza kuonekana bila login."""
    context = {
        'total_rooms': Room.objects.filter(house__is_available=True).count(),
        'total_users': User.objects.count(),
        'total_houses': House.objects.filter(is_available=True).count(),
    }
    return render(request, 'houses/home.html', context)


def available_rooms(request):
    """Ukurasa wa umma wa kuonyesha nyumba na vyumba vilivyopo."""
    houses = (
        House.objects.filter(is_available=True)
        .prefetch_related('rooms')
        .annotate(room_count=Count('rooms'), min_price=Min('rooms__price'))
        .order_by('-created_at')
    )

    selected_location = request.GET.get('location')
    if selected_location:
        houses = houses.filter(location=selected_location)

    total_houses = House.objects.filter(is_available=True).count()
    total_rooms = Room.objects.filter(house__is_available=True).count()
    locations = House.LOCATION_CHOICES

    context = {
        'houses': houses,
        'locations': locations,
        'selected_location': selected_location,
        'total_houses': total_houses,
        'total_rooms': total_rooms,
    }
    return render(request, 'houses/available_rooms.html', context)


# 1. ukurasa wa Nyumba Zote (Pamoja na ule Kichujio cha Maeneo)
@login_required
def house_list(request):
    houses = House.objects.filter(is_available=True).order_by('-created_at')
    
    selected_location = request.GET.get('location')
    if selected_location:
        houses = houses.filter(location=selected_location)
        
    locations = House.LOCATION_CHOICES
    
    context = {
        'houses': houses,
        'locations': locations,
        'selected_location': selected_location,
    }
    return render(request, 'houses/house_list.html', context)

# 2. Ukurasa wa Maelezo ya Ndani (Picha kubwa + Vyumba na Bei zake)
@login_required
def house_detail(request, pk):
    house = get_object_or_404(House, pk=pk)
    return render(request, 'houses/house_detail.html', {'house': house})




# def anzisha_malipo(request, house_id):
#     if request.method == 'POST':
#         phone_number = request.POST.get('phone_number')
#         amount = request.POST.get('amount')
#         room_id = request.POST.get('room_id')
        
#         # Mfano wa logic ya malipo (AzamPay / BeemSMS n.k.)
        
#         return redirect('house_detail', pk=house_id)