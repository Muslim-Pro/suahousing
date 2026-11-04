from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from accounts.models import Booking, LandlordApplication
from .models import House, Room


class AvailableRoomsSupportTests(TestCase):
    def test_available_rooms_uses_the_home_support_card(self):
        response = self.client.get(reverse('available_rooms'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="support-heading"')
        self.assertContains(response, 'How can we help?')
        self.assertContains(response, 'class="support-card text-center"')
        self.assertContains(response, 'class="support-option"')
        self.assertContains(response, 'Email support')
        self.assertContains(response, 'WhatsApp support')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertNotContains(response, 'Need Help Choosing a Room?')


class AvailableRoomsFilterTests(TestCase):
    def test_room_type_and_price_filters_match_the_same_room(self):
        landlord = User.objects.create_user(username='filter-landlord')
        mixed_house = House.objects.create(
            landlord=landlord,
            title='Mixed Price House',
            description='Contains differently priced room types.',
            location='mazimbu',
            address='Near SUA',
            image='house_images/mixed.png',
        )
        Room.objects.create(
            house=mixed_house,
            room_type='single',
            price=80000,
            room_image='room_images/mixed-single.png',
        )
        Room.objects.create(
            house=mixed_house,
            room_type='master',
            price=300000,
            room_image='room_images/mixed-master.png',
        )
        matching_house = House.objects.create(
            landlord=landlord,
            title='Matching Price House',
            description='A single room in the selected price range.',
            location='mazimbu',
            address='By the main gate',
            image='house_images/matching.png',
        )
        matching_room = Room.objects.create(
            house=matching_house,
            room_type='single',
            price=250000,
            room_image='room_images/matching-single.png',
        )

        response = self.client.get(
            reverse('available_rooms'),
            {'room_type': 'single', 'min_price': '200000', 'max_price': '275000'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['houses']), [matching_house])
        self.assertEqual(response.context['houses'][0].matching_rooms, [matching_room])
        self.assertContains(response, 'Matching Price House')
        self.assertNotContains(response, 'Mixed Price House')


class AvailableRoomsAvailabilityTests(TestCase):
    def test_listings_show_available_pending_and_booked_room_states(self):
        landlord = User.objects.create_user(username='availability-landlord')
        house = House.objects.create(
            landlord=landlord,
            title='Room Status House',
            description='Room availability status test.',
            location='mazimbu',
            address='Near SUA',
            image='house_images/room-status.png',
        )
        available_room = Room.objects.create(
            house=house,
            room_type='single',
            price=120000,
            room_image='room_images/available.png',
        )
        pending_room = Room.objects.create(
            house=house,
            room_type='double',
            price=150000,
            room_image='room_images/pending.png',
        )
        booked_room = Room.objects.create(
            house=house,
            room_type='master',
            price=200000,
            room_image='room_images/booked.png',
        )
        pending_student = User.objects.create_user(username='availability-pending')
        booked_student = User.objects.create_user(username='availability-booked')
        Booking.objects.create(
            student=pending_student,
            room=pending_room,
            status=Booking.STATUS_PENDING,
        )
        Booking.objects.create(
            student=booked_student,
            room=booked_room,
            status=Booking.STATUS_APPROVED,
        )

        response = self.client.get(reverse('available_rooms'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_rooms'], 2)
        self.assertContains(response, 'Requests pending · accepting requests')
        self.assertContains(response, '>Booked</span>')
        self.assertContains(response, '>Available</span>')
        visible_rooms = response.context['houses'][0].matching_rooms
        self.assertEqual(len(visible_rooms), 3)
        rooms_by_id = {room.pk: room for room in visible_rooms}
        self.assertFalse(rooms_by_id[available_room.pk].has_approved_booking)
        self.assertEqual(rooms_by_id[pending_room.pk].pending_booking_count, 1)
        self.assertTrue(rooms_by_id[booked_room.pk].has_approved_booking)


class ApprovedLandlordTrustIndicatorTests(TestCase):
    def test_only_admin_approved_landlords_get_verified_badges(self):
        approved_landlord = User.objects.create_user(username='approved-listing-landlord')
        LandlordApplication.objects.create(
            profile=approved_landlord.profile,
            property_address='Near SUA main gate',
            applicant_type=LandlordApplication.APPLICANT_OWNER,
            verification_details='Admin verified authority to list.',
            status=LandlordApplication.STATUS_APPROVED,
        )
        unreviewed_landlord = User.objects.create_user(username='unreviewed-listing-landlord')
        approved_house = House.objects.create(
            landlord=approved_landlord,
            title='Approved Landlord House',
            description='Reviewed landlord listing.',
            location='mazimbu',
            address='Near SUA main gate',
            image='house_images/approved-landlord.png',
        )
        unreviewed_house = House.objects.create(
            landlord=unreviewed_landlord,
            title='Unreviewed Landlord House',
            description='Unreviewed landlord listing.',
            location='town',
            address='Morogoro town',
            image='house_images/unreviewed-landlord.png',
        )
        Room.objects.create(
            house=approved_house,
            room_type='single',
            price=150000,
            room_image='room_images/approved-landlord.png',
        )
        Room.objects.create(
            house=unreviewed_house,
            room_type='single',
            price=160000,
            room_image='room_images/unreviewed-landlord.png',
        )
        student = User.objects.create_user(username='trust-indicator-student')
        self.client.force_login(student)

        listings_response = self.client.get(reverse('available_rooms'))
        houses_by_id = {house.pk: house for house in listings_response.context['houses']}
        self.assertTrue(houses_by_id[approved_house.pk].verified_landlord)
        self.assertFalse(houses_by_id[unreviewed_house.pk].verified_landlord)
        self.assertEqual(listings_response.content.decode().count('Admin-approved landlord'), 1)

        approved_detail = self.client.get(reverse('house_detail', args=[approved_house.pk]))
        unreviewed_detail = self.client.get(reverse('house_detail', args=[unreviewed_house.pk]))
        self.assertContains(approved_detail, 'Admin-approved landlord')
        self.assertNotContains(unreviewed_detail, 'Admin-approved landlord')


class HouseDetailContactLayoutTests(TestCase):
    def test_landlord_name_and_contact_buttons_share_a_flexible_row(self):
        landlord = User.objects.create_user(
            username='maliki-saidi',
            first_name='Maliki',
            last_name='Saidi',
            email='maliki@example.com',
        )
        landlord.profile.phone = '0712345678'
        landlord.profile.save(update_fields=['phone'])
        house = House.objects.create(
            landlord=landlord,
            title='Student Residence',
            description='Near campus.',
            location='mazimbu',
            address='Near SUA',
            image='house_images/student-residence.png',
        )
        student = User.objects.create_user(username='house-detail-student')
        self.client.force_login(student)

        response = self.client.get(reverse('house_detail', args=[house.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="landlord-contact-row mt-1"')
        self.assertContains(response, 'class="text-dark landlord-contact-name"')
        self.assertContains(response, 'text-transform: uppercase;')
        self.assertContains(response, 'font-weight: 600;')
        self.assertContains(response, 'height: 31px;')
        self.assertContains(response, 'padding: 0 1rem;')
        self.assertContains(response, '@media (max-width: 575.98px)')
        self.assertContains(response, 'padding-right: 0.65rem;')
        self.assertContains(response, 'padding-left: 0.65rem;')
        self.assertContains(response, 'flex-wrap: wrap;')
        self.assertContains(response, '@media (max-width: 767.98px)')
        self.assertContains(response, 'height: 360px;')
        self.assertContains(response, '@media (max-width: 575.98px)')
        self.assertContains(response, 'height: 300px;')
        self.assertContains(response, 'height: 160px;')
        self.assertContains(response, 'font-size: 11px;')
        self.assertContains(response, 'class="display-3 fw-bold mb-2"')
        self.assertContains(response, 'class="card p-4 border-0 shadow-sm rounded-3 bg-white house-about-card"')
        self.assertContains(response, 'class="btn btn-sm btn-outline-success rounded-pill landlord-contact-button"')
        self.assertContains(response, 'rounded-pill landlord-contact-button">\n                            <i class="fa-regular fa-envelope')
        self.assertContains(response, 'Maliki Saidi')
        self.assertContains(response, 'href="mailto:maliki@example.com"')
        self.assertContains(response, 'Contact landlord')
        self.assertContains(response, 'class="small text-danger fw-semibold report-listing-summary"')

    def test_house_detail_shows_room_count_with_correct_singular_and_plural(self):
        landlord = User.objects.create_user(username='room-count-landlord')
        house = House.objects.create(
            landlord=landlord,
            title='Room Count Residence',
            description='A house with several rooms.',
            location='mazimbu',
            address='Near SUA',
            image='house_images/room-count-residence.png',
        )
        student = User.objects.create_user(username='room-count-student')
        self.client.force_login(student)

        for room_number in range(3):
            Room.objects.create(
                house=house,
                room_type='single',
                price=150000,
                room_image=f'room_images/room-{room_number}.png',
            )

        response = self.client.get(reverse('house_detail', args=[house.pk]))

        self.assertContains(response, 'Rooms listed')
        self.assertContains(response, '3 rooms')
        self.assertEqual(response.context['house'].room_count, 3)

        Room.objects.filter(house=house).exclude(pk=Room.objects.filter(house=house).first().pk).delete()
        response = self.client.get(reverse('house_detail', args=[house.pk]))

        self.assertContains(response, '1 room')
        self.assertEqual(response.context['house'].room_count, 1)
