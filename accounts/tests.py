import re
import tempfile
import uuid
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from houses.models import House, Room
from houses.payments import ClickPesaError

from .models import (
    Booking,
    BookingMessage,
    Profile,
    SavedHouse,
    StudentNotification,
    SupportRequest,
)


def _image_upload(name):
    image_data = BytesIO()
    Image.new('RGB', (1, 1), color='white').save(image_data, format='PNG')
    return SimpleUploadedFile(name, image_data.getvalue(), content_type='image/png')


@override_settings(
    ALLOWED_HOSTS=['testserver', 'housing.example.com'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset-user',
            email='reset@example.com',
            password='Original-password-123!',
        )

    def test_valid_email_sends_reset_link_without_changing_password(self):
        response = self.client.post(
            reverse('forgot_password'),
            {'email': self.user.email},
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original-password-123!'))

    def test_reset_link_uses_https_behind_proxy(self):
        self.client.post(
            reverse('forgot_password'),
            {'email': self.user.email},
            HTTP_X_FORWARDED_PROTO='https',
            HTTP_HOST='housing.example.com',
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            'https://housing.example.com/accounts/reset/',
            mail.outbox[0].body,
        )

    def test_unknown_email_receives_same_confirmation_without_sending_email(self):
        response = self.client.post(
            reverse('forgot_password'),
            {'email': 'unknown@example.com'},
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_link_changes_password(self):
        self.client.post(reverse('forgot_password'), {'email': self.user.email})
        reset_path = re.search(
            r'http://testserver(?P<path>/accounts/reset/[^/\s]+/[^/\s]+/)',
            mail.outbox[0].body,
        ).group('path')

        response = self.client.get(reset_path)
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.url)
        self.assertContains(response, 'Choose a new password')

        response = self.client.post(
            response.request['PATH_INFO'],
            {
                'new_password1': 'A-new-secure-password-456!',
                'new_password2': 'A-new-secure-password-456!',
            },
        )

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('A-new-secure-password-456!'))

    def test_smtp_failure_does_not_break_reset_request(self):
        with patch(
            'accounts.forms.EmailMultiAlternatives.send',
            side_effect=OSError('SMTP unavailable'),
        ):
            with self.assertLogs('accounts.forms', level='ERROR'):
                response = self.client.post(
                    reverse('forgot_password'),
                    {'email': self.user.email},
                )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original-password-123!'))


class LandlordDashboardActionsTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username='landlord',
            password='Strong-password-123!',
        )
        profile = self.landlord.profile
        profile.user_type = 'landlord'
        profile.save(update_fields=['user_type'])
        self.client.login(username='landlord', password='Strong-password-123!')

    def test_dashboard_links_to_working_property_and_room_forms(self):
        response = self.client.get(reverse('landlord_dashboard'))

        self.assertContains(response, reverse('landlord_add_property'))
        self.assertContains(response, reverse('landlord_add_room'))
        self.assertContains(response, 'profile-dropdown')
        self.assertContains(response, 'profile-menu')
        self.assertContains(response, 'id="inquiries"')
        self.assertContains(response, 'id="payments"')
        self.assertContains(response, 'href="/#support"')

    def test_non_landlords_cannot_open_property_creation(self):
        student = User.objects.create_user(
            username='student',
            password='Strong-password-456!',
        )
        self.client.force_login(student)

        response = self.client.get(reverse('landlord_add_property'))

        self.assertRedirects(response, reverse('home'))

    def test_property_and_room_forms_use_english_labels(self):
        property_response = self.client.get(reverse('landlord_add_property'))

        self.assertContains(property_response, 'Property name')
        self.assertContains(property_response, 'Property description')
        self.assertContains(property_response, 'Location')
        self.assertContains(property_response, 'Nearby address')
        self.assertContains(property_response, 'Property exterior photo')
        self.assertNotContains(property_response, 'Jina la Nyumba/Hosteli')
        self.assertNotContains(property_response, 'Eneo Ilipo')

        house = House.objects.create(
            landlord=self.landlord,
            title='Green View',
            description='Student accommodation.',
            location='mazimbu',
            address='Near the main gate',
            image='house_images/green-view.png',
        )
        room_response = self.client.get(reverse('landlord_add_room'))

        self.assertContains(room_response, 'Property')
        self.assertContains(room_response, 'Room type')
        self.assertContains(room_response, 'Room price')
        self.assertContains(room_response, 'Room photo')
        self.assertContains(room_response, 'Master bedroom (private bathroom)')
        self.assertContains(room_response, 'Single room (shared bathroom)')
        self.assertNotContains(room_response, 'Aina ya Chumba')
        self.assertTrue(House.objects.filter(pk=house.pk).exists())

    def test_landlord_can_create_a_property_owned_by_their_account(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('landlord_add_property'),
                    {
                        'title': 'Green View',
                        'description': 'Student accommodation near campus.',
                        'location': 'mazimbu',
                        'address': 'Near the main gate',
                        'image': _image_upload('property.png'),
                    },
                )

        self.assertRedirects(response, reverse('landlord_dashboard'))
        house = House.objects.get(title='Green View')
        self.assertEqual(house.landlord, self.landlord)

    def test_landlord_can_add_a_room_to_their_property(self):
        house = House.objects.create(
            landlord=self.landlord,
            title='Green View',
            description='Student accommodation.',
            location='mazimbu',
            address='Near the main gate',
            image='house_images/green-view.png',
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('landlord_add_room'),
                    {
                        'house': house.pk,
                        'room_type': 'single',
                        'price': 120000,
                        'room_image': _image_upload('room.png'),
                        'description': 'Furnished room',
                    },
                )

        self.assertRedirects(response, reverse('landlord_dashboard'))
        self.assertTrue(Room.objects.filter(house=house, price=120000).exists())

    def test_landlord_cannot_add_a_room_to_another_landlords_property(self):
        another_landlord = User.objects.create_user(username='another-landlord')
        foreign_house = House.objects.create(
            landlord=another_landlord,
            title='Private House',
            description='Not this landlord property.',
            location='mazimbu',
            address='Private address',
            image='house_images/private.png',
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('landlord_add_room'),
                    {
                        'house': foreign_house.pk,
                        'room_type': 'single',
                        'price': 120000,
                        'room_image': _image_upload('room.png'),
                        'description': '',
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Room.objects.count(), 0)
        self.assertTrue(response.context['form'].errors)


class AuthenticationPageLayoutTests(TestCase):
    def test_login_uses_compact_authentication_header_and_footer(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'SUA Student Housing')
        self.assertContains(response, 'Browse rooms')
        self.assertContains(response, 'Need help? Contact us')
        self.assertContains(response, 'class="auth-main"')
        self.assertNotContains(response, 'Help &amp; Support')
        self.assertNotContains(response, 'href="/#support"')
        self.assertNotContains(response, 'Popular Locations')

    def test_authenticated_profile_dropdown_has_mobile_alignment_hook(self):
        user = User.objects.create_user(
            username='profile-user',
            password='Strong-password-123!',
        )
        Profile.objects.filter(user=user).update(user_type='landlord')
        self.client.force_login(user)

        response = self.client.get(reverse('home'))

        self.assertContains(response, 'navbar-profile-actions')
        self.assertContains(response, 'navbar-profile-menu')

    def test_registration_uses_compact_authentication_header_and_footer(self):
        response = self.client.get(reverse('register'))

        self.assertContains(response, 'SUA Student Housing')
        self.assertContains(response, 'Browse rooms')
        self.assertContains(response, 'Need help? Contact us')
        self.assertContains(response, 'class="auth-main"')
        self.assertNotContains(response, 'Help &amp; Support')
        self.assertNotContains(response, 'href="/#support"')
        self.assertContains(response, 'for="id_first_name"')
        self.assertNotContains(response, 'Popular Locations')

    def test_support_section_has_working_email_and_whatsapp_actions(self):
        response = self.client.get(reverse('home'))

        self.assertContains(response, 'id="support"')
        self.assertContains(response, 'href="mailto:suahousinginfo@gmail.com"')
        self.assertContains(response, 'href="https://wa.me/255614504540"')

    def test_footer_developer_credit_is_not_a_link(self):
        response = self.client.get(reverse('home'))

        self.assertContains(response, 'Developed by <strong class="text-white fw-bold">Pro_</strong>')
        self.assertNotContains(response, 'Pro_!')
        self.assertNotContains(response, 'href="/admin/"')


class StudentAccountSettingsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student-settings',
            password='Original-password-123!',
        )
        self.client.login(
            username='student-settings',
            password='Original-password-123!',
        )

    def test_student_can_open_settings_and_profile_menu_has_actions(self):
        response = self.client.get(
            reverse('account_settings'),
            {'section': 'profile_picture'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="profile-picture"')
        self.assertNotContains(response, 'id="change-password"')

        details_response = self.client.get(
            reverse('account_settings'),
            {'section': 'student_details'},
        )
        self.assertEqual(details_response.status_code, 200)
        self.assertContains(details_response, 'id="student-details"')
        self.assertContains(details_response, 'Save student details')
        self.assertContains(details_response, 'Emergency contact phone')
        for year in range(1, 6):
            self.assertContains(details_response, f'<option value="Year {year}">Year {year}</option>')
        self.assertContains(details_response, 'Enter the name of a trusted person')
        self.assertContains(details_response, '+255 712 345 678')
        self.assertNotContains(details_response, 'id="change-password"')

        password_response = self.client.get(
            reverse('account_settings'),
            {'section': 'change_password'},
        )
        self.assertContains(password_response, 'id="change-password"')
        self.assertNotContains(password_response, 'id="profile-picture"')
        self.assertNotContains(password_response, 'id="student-details"')

        home_response = self.client.get(reverse('home'))
        self.assertContains(
            home_response,
            f'href="{reverse("account_settings")}?section=profile_picture',
        )
        self.assertContains(
            home_response,
            f'href="{reverse("account_settings")}?section=change_password',
        )

    def test_student_returns_to_previous_page_after_updating_profile_picture(self):
        return_url = f'{reverse("available_rooms")}?location=mazimbu'
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('account_profile_picture'),
                    {
                        'profile_pic': _image_upload('student-profile.png'),
                        'next': return_url,
                    },
                )

        self.assertRedirects(response, return_url)
        self.student.profile.refresh_from_db()
        self.assertTrue(self.student.profile.profile_pic.name)

    def test_student_returns_to_previous_page_after_changing_password(self):
        return_url = f'{reverse("available_rooms")}?location=mazimbu'
        response = self.client.post(
            reverse('account_change_password'),
            {
                'old_password': 'Original-password-123!',
                'new_password1': 'New-student-password-456!',
                'new_password2': 'New-student-password-456!',
                'next': return_url,
            },
        )

        self.assertRedirects(response, return_url)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('New-student-password-456!'))
        self.assertEqual(self.client.get(return_url).status_code, 200)

    def test_invalid_student_password_change_shows_field_errors(self):
        return_url = reverse('house_list')
        response = self.client.post(
            reverse('account_change_password'),
            {
                'old_password': 'wrong-current-password',
                'new_password1': 'New-student-password-456!',
                'new_password2': 'New-student-password-456!',
                'next': return_url,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your old password was entered incorrectly.')
        self.assertContains(response, 'id="change-password"')
        self.assertNotContains(response, 'id="profile-picture"')

    def test_external_return_url_is_rejected(self):
        response = self.client.post(
            reverse('account_change_password'),
            {
                'old_password': 'Original-password-123!',
                'new_password1': 'New-student-password-456!',
                'new_password2': 'New-student-password-456!',
                'next': 'https://attacker.example/redirect',
            },
        )

        self.assertRedirects(response, reverse('house_list'))


class StudentDashboardTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='dashboard-student',
            first_name='Amina',
            email='amina@example.com',
            password='Strong-password-123!',
        )
        self.client.force_login(self.student)

    def test_dashboard_shows_real_available_listings_and_student_actions(self):
        landlord = User.objects.create_user(username='dashboard-landlord')
        available_house = House.objects.create(
            landlord=landlord,
            title='Campus View',
            description='Near SUA.',
            location='mazimbu',
            address='Near the main gate',
            image='house_images/campus-view.png',
        )
        Room.objects.create(
            house=available_house,
            room_type='single',
            price=150000,
            room_image='room_images/campus-view.png',
        )
        unavailable_house = House.objects.create(
            landlord=landlord,
            title='Unavailable House',
            description='Not open.',
            location='town',
            address='Town center',
            image='house_images/unavailable.png',
            is_available=False,
        )
        Room.objects.create(
            house=unavailable_house,
            room_type='single',
            price=100000,
            room_image='room_images/unavailable.png',
        )

        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['available_house_count'], 1)
        self.assertEqual(response.context['available_room_count'], 1)
        self.assertContains(response, 'Welcome, Amina!')
        self.assertContains(response, 'Campus View')
        self.assertContains(response, '150000')
        self.assertNotContains(response, 'Unavailable House')
        self.assertContains(response, reverse('student_dashboard'))
        self.assertContains(response, reverse('available_rooms'))
        self.assertContains(response, reverse('account_settings'))

    def test_student_login_redirects_to_student_dashboard(self):
        self.client.logout()

        response = self.client.post(
            reverse('login'),
            {
                'username': 'dashboard-student',
                'password': 'Strong-password-123!',
            },
        )

        self.assertRedirects(response, reverse('student_dashboard'))

    def test_profile_update_opens_two_account_options(self):
        response = self.client.get(reverse('student_dashboard'))

        self.assertContains(
            response,
            f'href="{reverse("account_settings")}?section=account_options&amp;next={reverse("student_dashboard")}"',
        )
        self.assertNotContains(response, 'accountOptionsModal')

        options_response = self.client.get(
            reverse('account_settings'),
            {'section': 'account_options', 'next': reverse('student_dashboard')},
        )
        self.assertContains(options_response, 'Update profile picture')
        self.assertContains(options_response, 'Change password')
        self.assertContains(
            options_response,
            f'href="{reverse("account_settings")}?section=profile_picture&amp;next={reverse("student_dashboard")}',
        )
        self.assertContains(
            options_response,
            f'href="{reverse("account_settings")}?section=change_password&amp;next={reverse("student_dashboard")}',
        )
        self.assertNotContains(options_response, '<div class="modal')

    def test_landlord_is_redirected_to_landlord_dashboard(self):
        landlord = User.objects.create_user(username='dashboard-landlord')
        landlord.profile.user_type = 'landlord'
        landlord.profile.save(update_fields=['user_type'])
        self.client.force_login(landlord)

        response = self.client.get(reverse('student_dashboard'))

        self.assertRedirects(response, reverse('landlord_dashboard'))

    def _create_room(self, landlord=None):
        landlord = landlord or User.objects.create_user(username='booking-landlord')
        landlord.profile.user_type = 'landlord'
        landlord.profile.save(update_fields=['user_type'])
        house = House.objects.create(
            landlord=landlord,
            title='Booking House',
            description='Near campus.',
            location='mazimbu',
            address='SUA main gate',
            image='house_images/booking-house.png',
        )
        room = Room.objects.create(
            house=house,
            room_type='single',
            price=175000,
            room_image='room_images/booking-room.png',
        )
        return house, room, landlord

    def test_student_can_update_all_student_details(self):
        response = self.client.post(
            reverse('account_settings') + '?section=student_details',
            {
                'section': 'student_details',
                'first_name': 'Amina',
                'last_name': 'Student',
                'phone': '0712345678',
                'university': 'Sokoine University of Agriculture',
                'year_of_study': 'Year 2',
                'emergency_contact_name': 'Fatuma',
                'emergency_contact_phone': '+255 754 123 456',
                'next': reverse('student_dashboard'),
            },
        )

        self.assertRedirects(response, reverse('student_dashboard'))
        self.student.refresh_from_db()
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.get_full_name(), 'Amina Student')
        self.assertEqual(self.student.profile.phone, '0712345678')
        self.assertEqual(self.student.profile.university, 'Sokoine University of Agriculture')
        self.assertEqual(self.student.profile.year_of_study, 'Year 2')
        self.assertEqual(self.student.profile.emergency_contact_name, 'Fatuma')
        self.assertEqual(self.student.profile.emergency_contact_phone, '+255 754 123 456')

    def test_student_details_reject_years_outside_the_selection(self):
        response = self.client.post(
            reverse('account_settings') + '?section=student_details',
            {
                'section': 'student_details',
                'first_name': 'Amina',
                'last_name': 'Student',
                'phone': '',
                'university': '',
                'year_of_study': 'Year 6',
                'emergency_contact_name': '',
                'emergency_contact_phone': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.year_of_study, '')

    def test_student_can_save_and_remove_a_home(self):
        house, _, _ = self._create_room()
        save_url = reverse('save_house', args=[house.pk])

        response = self.client.post(
            save_url,
            {'next': reverse('student_dashboard') + '#saved-homes'},
        )
        self.assertRedirects(
            response,
            reverse('student_dashboard') + '#saved-homes',
            fetch_redirect_response=False,
        )
        self.assertTrue(SavedHouse.objects.filter(student=self.student, house=house).exists())
        dashboard = self.client.get(reverse('student_dashboard'))
        self.assertContains(dashboard, house.title)

        self.client.post(save_url, {'next': reverse('student_dashboard') + '#saved-homes'})
        self.assertFalse(SavedHouse.objects.filter(student=self.student, house=house).exists())

    def test_room_details_offer_save_and_booking_actions(self):
        house, room, _ = self._create_room()

        response = self.client.get(reverse('house_detail', args=[house.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('save_house', args=[house.pk]))
        self.assertContains(response, reverse('apply_for_room', args=[room.pk]))
        self.assertContains(response, 'Book now')

    def test_paid_booking_can_download_pdf_receipt_from_dashboard_and_room(self):
        house, room, _ = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_PAID,
            payment_reference='SUA123ABC',
            payment_phone_number='255712345678',
        )

        dashboard_response = self.client.get(reverse('student_dashboard'))
        self.assertContains(
            dashboard_response,
            reverse('booking_payment_receipt', args=[booking.pk]),
        )
        self.assertContains(dashboard_response, 'Download PDF receipt')

        room_response = self.client.get(reverse('house_detail', args=[house.pk]))
        self.assertContains(
            room_response,
            reverse('booking_payment_receipt', args=[booking.pk]),
        )

        receipt_response = self.client.get(
            reverse('booking_payment_receipt', args=[booking.pk]),
        )
        self.assertEqual(receipt_response.status_code, 200)
        self.assertEqual(receipt_response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="payment-receipt-SUA123ABC.pdf"', receipt_response['Content-Disposition'])
        self.assertTrue(receipt_response.content.startswith(b'%PDF-'))
        booking.refresh_from_db()
        self.assertIsNotNone(booking.receipt_verification_token)

        verify_url = reverse(
            'verify_payment_receipt',
            kwargs={'token': booking.receipt_verification_token},
        )
        self.client.logout()
        verification_response = self.client.get(verify_url)
        self.assertContains(verification_response, 'Verified · Payment confirmed')
        self.assertContains(verification_response, 'SUA123ABC')
        self.assertContains(verification_response, 'Booking House')
        self.assertNotContains(verification_response, 'Amina')
        self.assertNotContains(verification_response, '255712345678')

    def test_unpaid_booking_cannot_download_receipt(self):
        _, room, _ = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_UNPAID,
        )

        response = self.client.get(
            reverse('booking_payment_receipt', args=[booking.pk]),
        )

        self.assertRedirects(response, reverse('student_dashboard'))

    def test_student_cannot_download_another_students_receipt(self):
        _, room, _ = self._create_room()
        other_student = User.objects.create_user(username='other-receipt-student')
        booking = Booking.objects.create(
            student=other_student,
            room=room,
            status=Booking.STATUS_APPROVED,
            payment_status=Booking.PAYMENT_PAID,
        )

        response = self.client.get(
            reverse('booking_payment_receipt', args=[booking.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_receipt_verification_token_does_not_verify_unpaid_booking(self):
        _, room, _ = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            payment_status=Booking.PAYMENT_UNPAID,
        )
        booking.receipt_verification_token = uuid.uuid4()
        booking.save(update_fields=['receipt_verification_token'])

        response = self.client.get(
            reverse(
                'verify_payment_receipt',
                kwargs={'token': booking.receipt_verification_token},
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_booking_request_reaches_landlord_and_can_be_approved(self):
        _, room, landlord = self._create_room()
        self.student.profile.phone = '0712345678'
        self.student.profile.university = 'Sokoine University of Agriculture'
        self.student.profile.year_of_study = 'Year 2'
        self.student.profile.emergency_contact_name = 'Fatuma Student'
        self.student.profile.emergency_contact_phone = '+255 754 123 456'
        self.student.profile.save()

        response = self.client.post(
            reverse('apply_for_room', args=[room.pk]),
            {'message': 'I am interested in viewing this room.'},
        )

        booking = Booking.objects.get(student=self.student, room=room)
        self.assertRedirects(response, reverse('student_dashboard'))
        self.assertEqual(booking.status, Booking.STATUS_PENDING)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_UNPAID)
        self.assertTrue(
            StudentNotification.objects.filter(
                recipient=landlord,
                booking=booking,
                notification_type=StudentNotification.TYPE_BOOKING,
            ).exists()
        )

        self.client.force_login(landlord)
        dashboard = self.client.get(reverse('landlord_dashboard'))
        self.assertContains(dashboard, 'Student details:')
        self.assertContains(dashboard, '0712345678')
        self.assertContains(dashboard, 'Sokoine University of Agriculture')
        self.assertContains(dashboard, 'Year 2')
        self.assertContains(dashboard, 'Fatuma Student')
        self.assertContains(dashboard, '+255 754 123 456')

        response = self.client.post(
            reverse('landlord_update_booking', args=[booking.pk]),
            {'action': 'approve'},
        )

        self.assertRedirects(response, reverse('landlord_dashboard'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.STATUS_APPROVED)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_UNPAID)
        self.assertTrue(
            StudentNotification.objects.filter(
                recipient=self.student,
                booking=booking,
                title='Booking request approved',
            ).exists()
        )

    def test_student_cannot_create_a_second_active_booking_for_the_same_room(self):
        _, room, _ = self._create_room()
        booking_url = reverse('apply_for_room', args=[room.pk])

        self.client.post(booking_url, {'message': 'First request.'})
        self.client.post(booking_url, {'message': 'Duplicate request.'})

        self.assertEqual(Booking.objects.filter(student=self.student, room=room).count(), 1)

    @patch('accounts.services.send_clickpesa_ussd_push')
    def test_approved_booking_starts_ussd_for_database_room_price(self, send_push):
        house, room, _ = self._create_room()
        house.is_available = False
        house.save(update_fields=['is_available'])
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
        )

        detail_response = self.client.get(reverse('house_detail', args=[house.pk]))
        self.assertContains(detail_response, 'Pay with USSD')
        self.assertContains(detail_response, f'id="room-{room.pk}"')

        response = self.client.post(
            reverse('initiate_booking_payment', args=[booking.pk]),
            {'phone_number': '0712 345 678'},
        )

        booking.refresh_from_db()
        self.assertRedirects(
            response,
            f'{reverse("house_detail", args=[house.pk])}#room-{room.pk}',
            fetch_redirect_response=False,
        )
        self.assertEqual(booking.payment_status, Booking.PAYMENT_PENDING)
        self.assertEqual(booking.payment_phone_number, '255712345678')
        self.assertTrue(booking.payment_reference.startswith('SUA'))
        send_push.assert_called_once_with(
            phone_number='255712345678',
            amount=room.price,
            order_reference=booking.payment_reference,
        )
        self.assertTrue(
            StudentNotification.objects.filter(
                recipient=self.student,
                booking=booking,
                title='USSD payment request sent',
            ).exists()
        )

    @patch('accounts.services.send_clickpesa_ussd_push')
    def test_student_cannot_pay_for_another_students_booking(self, send_push):
        _, room, _ = self._create_room()
        other_student = User.objects.create_user(username='other-payment-student')
        booking = Booking.objects.create(
            student=other_student,
            room=room,
            status=Booking.STATUS_APPROVED,
        )

        response = self.client.post(
            reverse('initiate_booking_payment', args=[booking.pk]),
            {'phone_number': '0712345678'},
        )

        self.assertEqual(response.status_code, 404)
        send_push.assert_not_called()

    @patch('accounts.services.send_clickpesa_ussd_push')
    def test_unapproved_booking_cannot_start_payment(self, send_push):
        _, room, _ = self._create_room()
        booking = Booking.objects.create(student=self.student, room=room)

        self.client.post(
            reverse('initiate_booking_payment', args=[booking.pk]),
            {'phone_number': '0712345678'},
        )

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_UNPAID)
        send_push.assert_not_called()

    @patch(
        'accounts.services.send_clickpesa_ussd_push',
        side_effect=ClickPesaError('Payment request rejected.'),
    )
    def test_definite_provider_rejection_resets_payment_state(self, send_push):
        _, room, _ = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
        )

        self.client.post(
            reverse('initiate_booking_payment', args=[booking.pk]),
            {'phone_number': '0712345678'},
        )

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_UNPAID)
        self.assertEqual(booking.payment_reference, '')
        self.assertEqual(booking.payment_phone_number, '')
        send_push.assert_called_once()

    @patch(
        'accounts.services.send_clickpesa_ussd_push',
        side_effect=ClickPesaError(
            'Push outcome unknown.',
            request_may_have_been_sent=True,
        ),
    )
    def test_unknown_provider_outcome_stays_pending_to_prevent_duplicate_push(self, send_push):
        _, room, _ = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
        )
        payment_url = reverse('initiate_booking_payment', args=[booking.pk])

        self.client.post(payment_url, {'phone_number': '0712345678'})
        self.client.post(payment_url, {'phone_number': '0712345678'})

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_PENDING)
        send_push.assert_called_once()

    def test_landlord_message_payment_reminder_and_confirmation_are_recorded(self):
        _, room, landlord = self._create_room()
        booking = Booking.objects.create(
            student=self.student,
            room=room,
            status=Booking.STATUS_APPROVED,
        )
        self.client.force_login(landlord)

        response = self.client.post(
            reverse('landlord_update_booking', args=[booking.pk]),
            {'action': 'message', 'message': 'Please call me to arrange a viewing.'},
        )
        self.assertRedirects(response, reverse('landlord_dashboard'))
        self.assertTrue(BookingMessage.objects.filter(booking=booking, sender=landlord).exists())
        self.assertTrue(
            StudentNotification.objects.filter(
                recipient=self.student,
                notification_type=StudentNotification.TYPE_MESSAGE,
            ).exists()
        )

        self.client.post(
            reverse('landlord_update_booking', args=[booking.pk]),
            {'action': 'payment_reminder'},
        )
        self.assertTrue(
            StudentNotification.objects.filter(
                recipient=self.student,
                notification_type=StudentNotification.TYPE_PAYMENT,
                title='Payment reminder',
            ).exists()
        )
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_UNPAID)

        self.client.post(
            reverse('landlord_update_booking', args=[booking.pk]),
            {'action': 'confirm_payment'},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_PAID)

    def test_landlord_cannot_update_another_landlords_booking(self):
        _, room, owner = self._create_room()
        self.student.profile.emergency_contact_phone = '+255 700 111 222'
        self.student.profile.save(update_fields=['emergency_contact_phone'])
        booking = Booking.objects.create(student=self.student, room=room)
        other_landlord = User.objects.create_user(username='other-booking-landlord')
        other_landlord.profile.user_type = 'landlord'
        other_landlord.profile.save(update_fields=['user_type'])
        self.client.force_login(other_landlord)

        response = self.client.post(
            reverse('landlord_update_booking', args=[booking.pk]),
            {'action': 'approve'},
        )

        self.assertEqual(response.status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.STATUS_PENDING)
        self.assertNotEqual(owner, other_landlord)
        dashboard = self.client.get(reverse('landlord_dashboard'))
        self.assertNotContains(dashboard, self.student.username)
        self.assertNotContains(dashboard, self.student.profile.emergency_contact_phone)

    def test_system_admin_can_view_student_emergency_details(self):
        self.student.profile.phone = '0712345678'
        self.student.profile.university = 'Sokoine University of Agriculture'
        self.student.profile.year_of_study = 'Year 2'
        self.student.profile.emergency_contact_name = 'Fatuma Student'
        self.student.profile.emergency_contact_phone = '+255 754 123 456'
        self.student.profile.save()
        admin_user = User.objects.create_superuser(
            username='system-admin',
            email='admin@example.com',
            password='Strong-admin-password-123!',
        )
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse('admin:accounts_profile_changelist'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sokoine University of Agriculture')
        self.assertContains(response, 'Fatuma Student')
        self.assertContains(response, '+255 754 123 456')

    def test_student_can_submit_support_request_and_view_dashboard_sections(self):
        response = self.client.post(
            reverse('submit_support_request'),
            {'message': 'I need help contacting a landlord.'},
        )

        self.assertRedirects(response, reverse('student_dashboard'))
        support_request = SupportRequest.objects.get(student=self.student)
        self.assertEqual(support_request.status, SupportRequest.STATUS_OPEN)

        dashboard = self.client.get(reverse('student_dashboard'))
        self.assertContains(dashboard, 'My Profile / Student Details')
        self.assertContains(dashboard, 'Saved Homes')
        self.assertContains(dashboard, 'My Bookings')
        self.assertContains(dashboard, 'Notifications &amp; Recent Activity')
        self.assertContains(dashboard, 'Help &amp; Support')
        self.assertContains(dashboard, 'I need help contacting a landlord.')

    def test_student_cannot_mark_another_users_notification_read(self):
        other_student = User.objects.create_user(username='another-student')
        notification = StudentNotification.objects.create(
            recipient=other_student,
            notification_type=StudentNotification.TYPE_BOOKING,
            title='Private notification',
            message='Only the recipient should see this.',
        )

        response = self.client.post(
            reverse('mark_notification_read', args=[notification.pk]),
        )

        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
