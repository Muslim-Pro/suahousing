from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

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
