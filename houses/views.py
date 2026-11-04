from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Exists, Min, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import HouseReportForm
from accounts.models import Booking, HouseReport, LandlordApplication, Review, SavedHouse
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
    approved_landlord_applications = LandlordApplication.objects.filter(
        profile__user_id=OuterRef('landlord_id'),
        status=LandlordApplication.STATUS_APPROVED,
    )
    houses = (
        House.objects.filter(is_available=True)
        .annotate(room_count=Count('rooms'), min_price=Min('rooms__price'))
        .annotate(verified_landlord=Exists(approved_landlord_applications))
        .order_by('-created_at')
    )

    selected_location = request.GET.get('location', '')
    # Kubali tu thamani zilizoorodheshwa ili URL zisizo sahihi zisilete filter batili.
    if selected_location not in dict(House.LOCATION_CHOICES):
        selected_location = ''
    if selected_location:
        houses = houses.filter(location=selected_location)

    selected_room_type = request.GET.get('room_type', '')
    if selected_room_type not in dict(Room.ROOM_TYPES):
        selected_room_type = ''
    min_price = _nonnegative_integer(request.GET.get('min_price'))
    max_price = _nonnegative_integer(request.GET.get('max_price'))
    room_filters = {}
    if selected_room_type:
        room_filters['room_type'] = selected_room_type
    if min_price is not None:
        room_filters['price__gte'] = min_price
    if max_price is not None:
        room_filters['price__lte'] = max_price
    visible_rooms = Room.objects.filter(**room_filters).annotate(
        has_approved_booking=Exists(
            Booking.objects.filter(
                room_id=OuterRef('pk'),
                status=Booking.STATUS_APPROVED,
            ),
        ),
        pending_booking_count=Count(
            'booking_requests',
            filter=Q(booking_requests__status=Booking.STATUS_PENDING),
            distinct=True,
        ),
    )
    if room_filters:
        # Exists huhakikisha aina na bei zinakutana kwenye chumba kimoja cha nyumba hiyo.
        houses = houses.filter(Exists(
            visible_rooms.filter(house_id=OuterRef('pk')),
        ))
    # Leta vyumba vinavyolingana tu ili ukurasa uonyeshe matokeo yaleyale yaliyotumika kuchuja.
    houses = houses.prefetch_related(
        Prefetch('rooms', queryset=visible_rooms, to_attr='matching_rooms'),
    )

    total_houses = House.objects.filter(is_available=True).count()
    total_rooms = Room.objects.filter(house__is_available=True).exclude(
        booking_requests__status=Booking.STATUS_APPROVED,
    ).distinct().count()
    locations = House.LOCATION_CHOICES

    context = {
        'houses': houses,
        'locations': locations,
        'room_types': Room.ROOM_TYPES,
        'selected_location': selected_location,
        'selected_room_type': selected_room_type,
        'min_price': min_price,
        'max_price': max_price,
        'total_houses': total_houses,
        'total_rooms': total_rooms,
    }
    return render(request, 'houses/available_rooms.html', context)


def _nonnegative_integer(value):
    # Thamani isiyo namba au hasi hupuuzwa badala ya kusababisha hitilafu ya query.
    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        return None
    return parsed_value if parsed_value >= 0 else None


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
    approved_landlord_applications = LandlordApplication.objects.filter(
        profile__user_id=OuterRef('landlord_id'),
        status=LandlordApplication.STATUS_APPROVED,
    )
    house = get_object_or_404(
        House.objects.select_related('landlord', 'landlord__profile').annotate(
            room_count=Count('rooms'),
            verified_landlord=Exists(approved_landlord_applications),
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

    booked_room_ids = set(
        Booking.objects.filter(
            room__house=house,
            status=Booking.STATUS_APPROVED,
        ).values_list('room_id', flat=True)
    )
    pending_room_ids = set(
        Booking.objects.filter(
            room__house=house,
            status=Booking.STATUS_PENDING,
        ).values_list('room_id', flat=True)
    )
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
        'booked_room_ids': booked_room_ids,
        'pending_room_ids': pending_room_ids,
        'student_phone': request.user.profile.phone if is_student else '',
        'landlord_whatsapp': tanzania_whatsapp_number(
            house.landlord.profile.phone,
        ),
        'house_reviews': Review.objects.filter(
            booking__room__house=house,
            booking__status=Booking.STATUS_APPROVED,
            booking__payment_status=Booking.PAYMENT_PAID,
        ).select_related('booking', 'booking__student'),
        'review_summary': Booking.objects.filter(
            room__house=house,
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_PAID,
            review__isnull=False,
        ).aggregate(average=Avg('review__rating'), count=Count('review')),
        'report_form': HouseReportForm(),
        'has_pending_report': is_student and HouseReport.objects.filter(
            house=house,
            reporter=request.user,
            status=HouseReport.STATUS_PENDING,
        ).exists(),
    }
    return render(request, 'houses/house_detail.html', context)
