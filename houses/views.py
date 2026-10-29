from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Min
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Booking, SavedHouse
from accounts.utils import tanzania_whatsapp_number
from .models import House, Room


def anzisha_malipo(request, house_id):
    messages.info(
        request,
        'To pay by USSD, submit a room request and wait for the landlord to approve it.',
    )
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
    rooms = list(house.rooms.all())
    approved_bookings_by_room = {}
    active_booking_room_ids = set()
    if is_student:
        approved_bookings_by_room = {
            booking.room_id: booking
            for booking in Booking.objects.filter(
                student=request.user,
                room__house=house,
                status=Booking.STATUS_APPROVED,
            ).select_related('room')
        }
        active_booking_room_ids = set(
            Booking.objects.filter(
                student=request.user,
                room__house=house,
                status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
            ).values_list('room_id', flat=True)
        )
    for room in rooms:
        room.approved_booking = approved_bookings_by_room.get(room.pk)

    context = {
        'house': house,
        'rooms': rooms,
        'is_student': is_student,
        'can_book': can_book,
        'is_saved': can_book and SavedHouse.objects.filter(
            student=request.user,
            house=house,
        ).exists(),
        'active_booking_room_ids': active_booking_room_ids,
        'student_phone': request.user.profile.phone if is_student else '',
        'landlord_whatsapp': tanzania_whatsapp_number(
            house.landlord.profile.phone,
        ),
    }
    return render(request, 'houses/house_detail.html', context)
