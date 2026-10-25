# Create your views here.


from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Min
from django.contrib.auth.models import User
from .models import House, Room
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
# kuhusu flutterwave, kuanzisha malipo na kudhibitisha matokeo ya maplipo 
import uuid
import hashlib
import hmac
import re
import requests
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from .models import House
import json
from django.http import JsonResponse
from accounts.models import Booking, SavedHouse
from accounts.utils import tanzania_whatsapp_number


def _format_tanzania_phone_number(phone_number):
    digits = re.sub(r"\D", "", phone_number)

    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("2550") and len(digits) == 13:
        digits = "255" + digits[4:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "255" + digits[1:]
    elif len(digits) == 9:
        digits = "255" + digits

    if digits.startswith("255") and len(digits) == 12 and digits[3] in "6789":
        return digits
    return None


def anzisha_malipo(request, house_id):
    if request.method == 'POST':
        phone_number = _format_tanzania_phone_number(
            request.POST.get('phone_number', '')
        )
        if not phone_number:
            messages.error(
                request,
                "Namba si sahihi. Weka namba ya Tanzania kama 0712345678 au 255712345678."
            )
            return redirect('house_detail', pk=house_id)

        amount = request.POST.get('amount', '1000')

        order_reference = f"SUA{uuid.uuid4().hex[:8].upper()}"

        client_id = getattr(settings, 'CLICKPESA_CLIENT_ID', '').strip()
        api_key = getattr(settings, 'CLICKPESA_API_KEY', '').strip()
        checksum_key = getattr(settings, 'CLICKPESA_CHECKSUM', '').strip()
        base_url = getattr(settings, 'CLICKPESA_BASE_URL', 'https://api.clickpesa.com/third-parties').strip().rstrip('/')

        if not checksum_key:
            messages.error(request, "ClickPesa checksum haijawekwa kwenye mipangilio ya seva.")
            return redirect('house_detail', pk=house_id)

        # ClickPesa tokens are valid for one hour; reuse one to avoid rate limits.
        token_cache_key = "clickpesa_token_" + hashlib.sha256(
            f"{base_url}:{client_id}:{api_key}:{checksum_key}".encode('utf-8')
        ).hexdigest()
        jwt_token = cache.get(token_cache_key)

        token_url = f"{base_url}/generate-token"
        token_headers = {
            "client-id": client_id,
            "api-key": api_key,
            "Content-Type": "application/json"
        }

        try:
            if not jwt_token:
                token_res = requests.post(token_url, headers=token_headers, timeout=15)

                if token_res.status_code not in [200, 201]:
                    messages.error(request, f"ClickPesa Token Error ({token_res.status_code}): {token_res.text}")
                    return redirect('house_detail', pk=house_id)

                token_data = token_res.json()
                jwt_token = token_data.get("token") or token_data.get("accessToken")

                if not jwt_token:
                    messages.error(request, f"Token was not found in the response from ClickPesa: {token_data}")
                    return redirect('house_detail', pk=house_id)

                cache.set(token_cache_key, jwt_token, timeout=55 * 60)

            # 2. TUMA USSD PUSH REQUEST
            push_url = f"{base_url}/payments/initiate-ussd-push-request"
            push_headers = {
                "Authorization": jwt_token,
                "Content-Type": "application/json"
            }

            payload = {
                "amount": str(amount),
                "currency": "TZS",
                "orderReference": order_reference,
                "phoneNumber": phone_number
            }
            payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            payload_checksum = hmac.new(
                checksum_key.encode('utf-8'),
                payload_json.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            payload['checksum'] = payload_checksum

            push_res = requests.post(push_url, json=payload, headers=push_headers, timeout=15)
            
            if push_res.status_code in [200, 201, 202]:
                messages.success(request, f"Request for payment has been sent to the phone number ({phone_number}). Please enter your PIN to complete the transaction.")
            else:
                messages.error(
                    request,
                    "Insufficient funds in your mobile money account. Please recharge your account and try again."
                )

        except Exception as e:
            messages.error(request, f"Connection timed out: The payment server is taking too longer to respond. Please check your internet connection and try again.")

        return redirect('house_detail', pk=house_id)

    return redirect('house_detail', pk=house_id)


def home(request):
    """Ukurasa wa kukaribisha — unaoweza kuonekana bila login."""
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


# 1. ukurasa wa Nyumba Zote na filter by location
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
    house = get_object_or_404(
        House.objects.select_related('landlord', 'landlord__profile').annotate(
            room_count=Count('rooms'),
        ),
        pk=pk,
    )
    is_student = request.user.user_type == 'student'
    can_book = is_student and house.is_available
    context = {
        'house': house,
        'is_student': is_student,
        'can_book': can_book,
        'is_saved': can_book and SavedHouse.objects.filter(
            student=request.user,
            house=house,
        ).exists(),
        'active_booking_room_ids': (
            Booking.objects.filter(
                student=request.user,
                room__house=house,
                status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
            ).values_list('room_id', flat=True)
            if can_book else []
        ),
        'landlord_whatsapp': tanzania_whatsapp_number(
            house.landlord.profile.phone,
        ),
    }
    return render(request, 'houses/house_detail.html', context)
