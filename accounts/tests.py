import re
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from houses.models import House, Room

from .models import Profile


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

        password_response = self.client.get(
            reverse('account_settings'),
            {'section': 'change_password'},
        )
        self.assertContains(password_response, 'id="change-password"')
        self.assertNotContains(password_response, 'id="profile-picture"')

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
