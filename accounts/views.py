from django.shortcuts import get_object_or_404, redirect, render
from .models import Profile
from .forms import UserForm , ProfileForm , UserCreateForm
from django.contrib.auth.views import PasswordResetView
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.core.mail import mail_admins
from property.models import *
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponseRedirect
from django.db import transaction
import stripe

from project.audit import get_client_ip, security_log

# Create your views here.


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def booking_audit_snapshot(booking):
    return {
        'id': booking.id,
        'user_id': booking.user_id,
        'property_id': booking.property_id,
        'stripe_session_id': booking.stripe_session_id,
        'date_from': booking.date_from.isoformat() if booking.date_from else None,
        'date_to': booking.date_to.isoformat() if booking.date_to else None,
        'guest': booking.guest,
        'children': booking.children,
        'status': booking.status,
        'cancelled_at': booking.cancelled_at.isoformat() if booking.cancelled_at else None,
        'cancelled_by_id': booking.cancelled_by_id,
        'cancellation_ip_address': booking.cancellation_ip_address,
    }


def sync_booking_payment_status(booking):
    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if (
        booking.status != 'pending'
        or not getattr(booking, 'stripe_session_id', None)
        or not stripe_key
    ):
        return booking

    try:
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.retrieve(booking.stripe_session_id)
        payment_status = getattr(session, 'payment_status', None)
        session_status = getattr(session, 'status', None)
        if payment_status == 'paid' or session_status == 'complete':
            booking.status = 'confirmed'
            booking.save(update_fields=['status'])
            security_log.info(
                'booking.payment.confirmed booking_id=%s user_id=%s source=reservation_sync',
                booking.id,
                booking.user_id,
            )
    except Exception:
        # Non-fatal: leave the booking as-is if Stripe lookup fails.
        security_log.warning(
            'booking.payment.sync_failed booking_id=%s stripe_session_id=%s',
            booking.id,
            booking.stripe_session_id,
            exc_info=True,
        )

    return booking

def signup(request):
    if request.method == 'POST':
        signup_form = UserCreateForm(request.POST)
        if signup_form.is_valid():
            created_user = signup_form.save()
            security_log.info(
                'auth.signup.success user_id=%s username=%s ip=%s',
                created_user.id,
                created_user.username,
                get_client_ip(request),
            )
            # return redirect(reverse('login'))
            username = signup_form.cleaned_data['username']
            password = signup_form.cleaned_data['password1']
            user = authenticate(request, username=username, password=password)
            login(request,user)
            return redirect(reverse('accounts:profile'))
    
    else:
        signup_form = UserCreateForm()

    return render(request,'registration/signup.html',{'signup_form':signup_form})


class SafePasswordResetView(PasswordResetView):
    def form_valid(self, form):
        security_log.info(
            'auth.password_reset.request email=%s ip=%s',
            form.cleaned_data.get('email'),
            get_client_ip(self.request),
        )
        form.save(
            use_https=getattr(settings, 'PASSWORD_RESET_PROTOCOL', 'https') == 'https',
            token_generator=self.token_generator,
            from_email=self.from_email,
            email_template_name=self.email_template_name,
            subject_template_name=self.subject_template_name,
            request=self.request,
            html_email_template_name=self.html_email_template_name,
            extra_email_context=self.extra_email_context,
            domain_override=getattr(settings, 'PASSWORD_RESET_DOMAIN', None),
        )
        return HttpResponseRedirect(self.get_success_url())



@login_required
def profile(request):
    profile = get_object_or_404(Profile, user=request.user)
    return render(request,'profile/profile.html',{'profile':profile})



@login_required
def profile_edit(request):
    profile = get_object_or_404(Profile, user=request.user)
    if request.method == 'POST':
        user_form = UserForm(request.POST , instance=request.user)
        profile_form = ProfileForm(request.POST , request.FILES , instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            my_form = profile_form.save(commit=False)
            my_form.user = request.user
            my_form.save()
            security_log.info(
                'profile.edit user_id=%s profile_id=%s ip=%s',
                request.user.id,
                profile.id,
                get_client_ip(request),
            )
            messages.success(request, 'Profile details updated.')
            return redirect(reverse('accounts:profile'))
    
    else:
        user_form = UserForm(instance=request.user)
        profile_form = ProfileForm(instance = profile)       

    return render(request,'profile/profile_edit.html',{
        'user_form' : user_form , 
        'profile_form' : profile_form
    })
    
    

@login_required
def myreservation(request):
    # Build a list of bookings with extra context for reservation actions.
    from django.utils import timezone
    bookings = PropertyBook.objects.filter(user=request.user).order_by('-id')
    booking_entries = []
    today = timezone.localdate()
    for b in bookings:
        b = sync_booking_payment_status(b)
        can_cancel = False
        try:
            if b.status != 'cancelled' and b.date_from >= today:
                can_cancel = True
        except Exception:
            can_cancel = False
            security_log.warning(
                'booking.cancelability_check_failed booking_id=%s user_id=%s',
                b.id,
                request.user.id,
                exc_info=True,
            )
        booking_entries.append({
            'booking': b,
            'can_cancel': can_cancel,
        })

    return render(request, 'profile/reservations.html', {'booking_list': booking_entries})


@login_required
def cancel_reservation(request, pk):
    # Allow the booking owner to cancel a booking before check-in date
    from django.utils import timezone
    try:
        booking = PropertyBook.objects.get(id=pk)
    except PropertyBook.DoesNotExist:
        security_log.warning(
            'booking.cancel.missing booking_id=%s actor_user_id=%s ip=%s',
            pk,
            request.user.id,
            get_client_ip(request),
        )
        return redirect('accounts:reservation')

    if booking.user != request.user:
        security_log.warning(
            'booking.cancel.denied booking_id=%s actor_user_id=%s owner_user_id=%s ip=%s',
            booking.id,
            request.user.id,
            booking.user_id,
            get_client_ip(request),
        )
        return redirect('accounts:reservation')

    booking = sync_booking_payment_status(booking)
    today = timezone.localdate()
    if request.method == 'POST':
        if booking.date_from >= today and booking.status != 'cancelled':
            cancelled_at = timezone.now()
            ip_address = get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            before_snapshot = booking_audit_snapshot(booking)
            previous_status = booking.status

            with transaction.atomic():
                booking.status = 'cancelled'
                booking.cancelled_at = cancelled_at
                booking.cancelled_by = request.user
                booking.cancellation_ip_address = ip_address
                booking.save(update_fields=[
                    'status',
                    'cancelled_at',
                    'cancelled_by',
                    'cancellation_ip_address',
                ])

                BookingCancellationAudit.objects.create(
                    booking=booking,
                    actor=request.user,
                    cancelled_at=cancelled_at,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    previous_status=previous_status,
                    new_status=booking.status,
                    before_snapshot=before_snapshot,
                    after_snapshot=booking_audit_snapshot(booking),
                )
        return redirect('accounts:reservation')
    # If GET, redirect back
    return redirect('accounts:reservation')

@login_required
def mylisting(request):
    property_list = Property.objects.filter(owner=request.user).order_by('-created_at', '-id')
    return render(request , 'profile/mylisting.html', {'property_list' : property_list})


@login_required
def become_host(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.is_host:
        messages.info(request, 'Your account is already approved for hosting.')
        return redirect(reverse('accounts:profile'))

    if profile.host_requested:
        messages.info(request, 'Your host application is already under review.')
        return redirect(reverse('accounts:profile'))

    if request.method == 'POST':
        profile.host_requested = True
        profile.save(update_fields=['host_requested'])
        security_log.info(
            'host.application.submitted user_id=%s username=%s ip=%s',
            request.user.id,
            request.user.username,
            get_client_ip(request),
        )
        mail_admins(
            'Host application',
            (
                f'User {request.user.username} applied for host status.\n'
                f'Email: {request.user.email or "(no email provided)"}\n'
                f'User ID: {request.user.id}'
            ),
        )
        messages.info(request, 'Your host application has been submitted and is under review.')
        return redirect(reverse('accounts:profile'))

    return render(request, 'profile/become_host_confirm.html', {})
