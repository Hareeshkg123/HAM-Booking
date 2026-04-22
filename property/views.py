from typing import Any, Dict
from django.shortcuts import redirect, render
import stripe
from django.views.generic import ListView , DetailView , CreateView
from .models import *
from django.views.generic.edit import FormMixin
from .forms import *
from .filters import *
from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from typing import Any, Dict
from django.shortcuts import redirect, render
import stripe
from django.views.generic import ListView , DetailView , CreateView
from .models import *
from django.views.generic.edit import FormMixin
from .forms import *
from .filters import *
from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from accounts.models import Profile
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

# Create your views here.


class PropertyList(FilterView):
    model = Property
    paginate_by = 6
    filterset_class = PropertyFilter
    template_name = 'property/property_list.html'


class PropertyDetail(FormMixin, DetailView):
    model = Property
    template_name = 'property/property_detail.html'
    form_class = PropertyBookForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related"] = Property.objects.filter(category=self.get_object().category)[:3]
        # include current user's latest booking for this property (if any)
        user_booking = None
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            user_booking = PropertyBook.objects.filter(property=self.get_object(), user=self.request.user).order_by('-id').first()
        # If Stripe redirected back with a session_id, try to confirm the booking immediately (useful for testing without webhooks)
        session_id = self.request.GET.get('session_id')
        if session_id and getattr(settings, 'STRIPE_SECRET_KEY', None):
            try:
                stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY')
                sess = stripe.checkout.Session.retrieve(session_id)
                # Stripe's Checkout Session may include metadata.booking_id
                metadata = sess.get('metadata', {}) or {}
                booking_id = metadata.get('booking_id')
                payment_status = getattr(sess, 'payment_status', None) or sess.get('payment_status')
                # consider 'paid' as successful
                if booking_id and payment_status == 'paid':
                    try:
                        booking = PropertyBook.objects.get(id=int(booking_id))
                        if booking.status != 'confirmed':
                            booking.status = 'confirmed'
                            booking.save()
                            user_booking = booking
                    except PropertyBook.DoesNotExist:
                        pass
            except Exception:
                # Non-fatal: if Stripe lookup fails, continue without changing booking
                pass

        context['user_booking'] = user_booking
        return context

    def post(self, request, *args, **kwargs):
        # require login for booking — redirect anonymous users to the login page
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        form = self.get_form()
        if form.is_valid():
            myform = form.save(commit=False)
            myform.property = self.get_object()
            myform.user = request.user
            # mark booking as pending — we'll confirm after successful payment webhook
            myform.status = 'pending'
            myform.save()

            # Attempt to create a Stripe Checkout session if API key is configured.
            stripe_secret = getattr(settings, 'STRIPE_SECRET_KEY', None)
            if stripe_secret:
                try:
                    stripe.api_key = stripe_secret
                    session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{
                            'price_data': {
                                'currency': 'usd',
                                'unit_amount': int(self.get_object().price * 100),
                                'product_data': {'name': self.get_object().name},
                            },
                            'quantity': 1,
                        }],
                        mode='payment',
                        success_url=request.build_absolute_uri(self.get_object().get_absolute_url()) + '?booking=success&session_id={CHECKOUT_SESSION_ID}',
                        cancel_url=request.build_absolute_uri(self.get_object().get_absolute_url()) + '?booking=cancelled',
                        # attach booking id so we can confirm it in the webhook handler
                        metadata={
                            'booking_id': str(myform.id),
                        },
                    )
                    return redirect(session.url)
                except Exception:
                    # If Stripe fails, continue and show pending page locally
                    return redirect(self.get_object().get_absolute_url())

            # If no Stripe configured, just redirect back to property detail with pending state
            return redirect(self.get_object().get_absolute_url())
        else:
            # re-render the detail page with form errors
            return self.get(request, *args, **kwargs)


class AddListing(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'property/property_add.html'
    success_url = reverse_lazy('property:property_list')
    login_url = reverse_lazy('login')

    def test_func(self):
        # allow only users whose Profile.is_host is True
        if not self.request.user.is_authenticated:
            return False
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return bool(profile.is_host)

    def handle_no_permission(self):
        # if user isn't a host, redirect to profile page (could be adjusted)
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return redirect(reverse_lazy('accounts:profile'))

    def form_valid(self, form):
        # set the owner to the logged-in user
        form.instance.owner = self.request.user
        return super().form_valid(form)


@csrf_exempt
def stripe_webhook(request):
    """Endpoint to receive Stripe webhooks and confirm bookings on successful payment."""
    import stripe as _stripe
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    if webhook_secret:
        try:
            event = _stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            # Invalid payload
            return HttpResponse(status=400)
        except _stripe.error.SignatureVerificationError:
            # Invalid signature
            return HttpResponse(status=400)
    else:
        # No webhook secret configured: try to parse without verification (development only)
        try:
            event = _stripe.Event.construct_from(_stripe.util.json.loads(payload), _stripe.api_key)
        except Exception:
            return HttpResponse(status=400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {}) or {}
        booking_id = metadata.get('booking_id')
        if booking_id:
            try:
                booking = PropertyBook.objects.get(id=int(booking_id))
                booking.status = 'confirmed'
                booking.save()
            except PropertyBook.DoesNotExist:
                # nothing to do if booking not found
                pass

    return HttpResponse(status=200)


