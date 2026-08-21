# from django.shortcuts import render

# Create your views here.


from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Min
from django.contrib.auth.models import User
from .models import House, Room
from django.contrib.auth.decorators import login_required


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