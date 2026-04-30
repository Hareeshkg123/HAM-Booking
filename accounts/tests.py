from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from axes.models import AccessAttempt
from axes.utils import reset

from accounts.models import Profile
from accounts.views import sync_booking_payment_status
from property.models import BookingCancellationAudit, Category, Place, Property, PropertyBook


class ReservationActionsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='guest', password='secret123')
        self.other_user = User.objects.create_user(username='host', password='secret123')

        image = SimpleUploadedFile('test.jpg', b'filecontent', content_type='image/jpeg')
        self.place = Place.objects.create(name='Cairo', image=image)
        self.category = Category.objects.create(name='Apartment', icon='home')
        self.property = Property.objects.create(
            owner=self.other_user,
            name='Test Stay',
            image=SimpleUploadedFile('property.jpg', b'filecontent', content_type='image/jpeg'),
            price=120,
            description='Nice place',
            places=self.place,
            category=self.category,
        )

        today = timezone.localdate()
        self.cancelled_booking = PropertyBook.objects.create(
            user=self.user,
            property=self.property,
            date_from=today + timedelta(days=5),
            date_to=today + timedelta(days=7),
            guest=1,
            children=1,
            status='cancelled',
        )
        self.confirmed_booking = PropertyBook.objects.create(
            user=self.user,
            property=self.property,
            date_from=today - timedelta(days=3),
            date_to=today - timedelta(days=1),
            guest=1,
            children=1,
            status='confirmed',
        )

        self.client.login(username='guest', password='secret123')

    def test_reservations_page_shows_cancelled_booking_without_delete_action(self):
        response = self.client.get(reverse('accounts:reservation'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Status:</strong>')
        self.assertContains(response, 'Cancelled')
        self.assertNotContains(response, 'Cannot cancel')
        self.assertNotContains(response, 'Delete booking')

    def test_same_day_booking_can_be_cancelled(self):
        today = timezone.localdate()
        booking = PropertyBook.objects.create(
            user=self.user,
            property=self.property,
            date_from=today,
            date_to=today + timedelta(days=2),
            guest=1,
            children=0,
            status='pending',
        )

        response = self.client.post(
            reverse('accounts:cancel_reservation', args=[booking.id]),
            HTTP_X_FORWARDED_FOR='203.0.113.9',
            HTTP_USER_AGENT='AuditTrailTest/1.0',
        )

        self.assertRedirects(response, reverse('accounts:reservation'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.cancelled_by, self.user)
        self.assertEqual(booking.cancellation_ip_address, '203.0.113.9')

        audit = BookingCancellationAudit.objects.get(booking=booking)
        self.assertEqual(audit.actor, self.user)
        self.assertEqual(audit.ip_address, '203.0.113.9')
        self.assertEqual(audit.user_agent, 'AuditTrailTest/1.0')
        self.assertEqual(audit.previous_status, 'pending')
        self.assertEqual(audit.new_status, 'cancelled')
        self.assertEqual(audit.before_snapshot['status'], 'pending')
        self.assertEqual(audit.after_snapshot['status'], 'cancelled')
        self.assertIsNone(audit.before_snapshot['cancelled_at'])
        self.assertIsNotNone(audit.after_snapshot['cancelled_at'])

    @patch('accounts.views.stripe.checkout.Session.retrieve')
    @patch('accounts.views.settings.STRIPE_SECRET_KEY', 'test_secret')
    def test_pending_paid_booking_is_reconciled_to_confirmed(self, mock_retrieve):
        mock_session = Mock()
        mock_session.get.return_value = 'paid'
        mock_retrieve.return_value = mock_session

        booking = PropertyBook.objects.create(
            user=self.user,
            property=self.property,
            stripe_session_id='cs_test_123',
            date_from=timezone.localdate() + timedelta(days=3),
            date_to=timezone.localdate() + timedelta(days=5),
            guest=1,
            children=0,
            status='pending',
        )

        response = self.client.get(reverse('accounts:reservation'))

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')

    @patch('accounts.views.stripe.checkout.Session.retrieve', side_effect=RuntimeError('stripe down'))
    @patch('accounts.views.settings.STRIPE_SECRET_KEY', 'test_secret')
    def test_payment_sync_failure_is_logged(self, mock_retrieve):
        booking = PropertyBook.objects.create(
            user=self.user,
            property=self.property,
            stripe_session_id='cs_test_error',
            date_from=timezone.localdate() + timedelta(days=3),
            date_to=timezone.localdate() + timedelta(days=5),
            guest=1,
            children=0,
            status='pending',
        )

        with self.assertLogs('security', level='WARNING') as captured_logs:
            sync_booking_payment_status(booking)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')
        self.assertTrue(
            any('booking.payment.sync_failed' in message for message in captured_logs.output)
        )


class ProfileAccessControlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='member', password='secret123')

    def test_profile_requires_login(self):
        response = self.client.get(reverse('accounts:profile'))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('accounts:profile')}")

    def test_profile_edit_requires_login(self):
        response = self.client.get(reverse('accounts:profile_edit'))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('accounts:profile_edit')}")


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    ADMINS=[('Admin', 'admin@example.com')],
)
class BecomeHostWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='secret123',
        )
        self.profile = Profile.objects.get(user=self.user)
        self.client.login(username='member', password='secret123')

    def test_become_host_creates_pending_request_without_promoting_user(self):
        response = self.client.post(reverse('accounts:become_host'), follow=True)

        self.assertRedirects(response, reverse('accounts:profile'))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_host)
        self.assertTrue(self.profile.host_requested)
        self.assertContains(response, 'under review')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Host application', mail.outbox[0].subject)
        self.assertIn('User member applied for host status.', mail.outbox[0].body)

    def test_repeat_host_request_is_blocked(self):
        self.profile.host_requested = True
        self.profile.save(update_fields=['host_requested'])

        response = self.client.post(reverse('accounts:become_host'), follow=True)

        self.assertRedirects(response, reverse('accounts:profile'))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_host)
        self.assertTrue(self.profile.host_requested)
        self.assertContains(response, 'already under review')
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    AXES_FAILURE_LIMIT=2,
    AXES_COOLOFF_TIME=1,
    AXES_RESET_ON_SUCCESS=True,
    AXES_LOCKOUT_TEMPLATE=None,
    AXES_LOCKOUT_PARAMETERS=['username', 'ip_address'],
    AXES_HTTP_RESPONSE_CODE=403,
)
class LoginBruteForceProtectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='lockeduser',
            email='locked@example.com',
            password='secret123',
        )

    def tearDown(self):
        reset(ip='127.0.0.1', username=self.user.username, ip_or_username=True)

    def test_login_is_locked_after_repeated_failed_attempts(self):
        login_url = reverse('login')

        first_response = self.client.post(
            login_url,
            {'username': self.user.username, 'password': 'wrong-1'},
        )
        second_response = self.client.post(
            login_url,
            {'username': self.user.username, 'password': 'wrong-2'},
        )
        locked_response = self.client.post(
            login_url,
            {'username': self.user.username, 'password': 'secret123'},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 403)
        self.assertEqual(locked_response.status_code, 403)
        self.assertFalse('_auth_user_id' in self.client.session)
        self.assertTrue(
            AccessAttempt.objects.filter(username=self.user.username).exists()
        )


@override_settings(AXES_ENABLED=False)
class AuthenticationAuditLoggingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='audit-user',
            email='audit@example.com',
            password='secret123',
        )

    def test_successful_login_is_logged(self):
        with self.assertLogs('security', level='INFO') as captured_logs:
            response = self.client.post(
                reverse('login'),
                {'username': self.user.username, 'password': 'secret123'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            any('auth.login.success' in message for message in captured_logs.output)
        )


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    ALLOWED_HOSTS=['testserver', 'evil.com'],
    PASSWORD_RESET_DOMAIN='ham-booking.example.com',
    PASSWORD_RESET_PROTOCOL='https',
)
class PasswordResetHostHeaderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='secret123',
        )

    def test_password_reset_email_uses_trusted_domain_not_host_header(self):
        response = self.client.post(
            reverse('password_reset'),
            {'email': self.user.email},
            HTTP_HOST='evil.com',
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('https://ham-booking.example.com/', mail.outbox[0].body)
        self.assertNotIn('evil.com', mail.outbox[0].body)
