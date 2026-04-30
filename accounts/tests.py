from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
