from django.shortcuts import redirect, render
from .models import Profile
from .forms import UserForm , ProfileForm , UserCreateForm
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib import messages
from property.models import *
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
import stripe

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
    except Exception:
        # Non-fatal: leave the booking as-is if Stripe lookup fails.
        pass

    return booking

def signup(request):
    if request.method == 'POST':
        signup_form = UserCreateForm(request.POST)
        if signup_form.is_valid():
            signup_form.save()
            # return redirect(reverse('login'))
            username = signup_form.cleaned_data['username']
            password = signup_form.cleaned_data['password1']
            user = authenticate(username=username,password=password)
            login(request,user)
            return redirect(reverse('accounts:profile'))
    
    else:
        signup_form = UserCreateForm()

    return render(request,'registration/signup.html',{'signup_form':signup_form})



def profile(request):
    profile = Profile.objects.get(user = request.user)
    return render(request,'profile/profile.html',{'profile':profile})



@login_required
def profile_edit(request):
    profile = Profile.objects.get(user = request.user)
    if request.method == 'POST':
        user_form = UserForm(request.POST , instance=request.user)
        profile_form = ProfileForm(request.POST , request.FILES , instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            my_form = profile_form.save(commit=False)
            my_form.user = request.user
            my_form.save()
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
        return redirect('accounts:reservation')

    if booking.user != request.user:
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

def mylisting(request):
    property_list = Property.objects.filter(owner=request.user)
    return render(request , 'profile/mylisting.html', {'property_list' : property_list})


@login_required
def become_host(request):
    # Allow users to enable hosting for their account. This is a simple
    # immediate enable; in production you may want an approval workflow.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        profile.is_host = True
        profile.save()
        messages.success(request, 'You are now a host. You can add listings.')
        return redirect(reverse('accounts:profile'))

    return render(request, 'profile/become_host_confirm.html', {})
