from django.shortcuts import redirect, render
from .models import Profile
from .forms import UserForm , ProfileForm , UserCreateForm
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib import messages
from property.models import *
from django.contrib.auth.decorators import login_required
from django.conf import settings
import stripe

# Create your views here.

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
    # Build a list of bookings with extra context (can_cancel) for the template
    from django.utils import timezone
    bookings = PropertyBook.objects.filter(user=request.user).order_by('-id')
    booking_entries = []
    today = timezone.localdate()
    # Attempt lightweight reconciliation for pending bookings that have a saved
    # stripe_session_id: if Stripe reports the session is paid, mark confirmed.
    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if stripe_key:
        try:
            stripe.api_key = stripe_key
        except Exception:
            stripe.api_key = None
    for b in bookings:
        # If booking appears pending but has a Stripe session id, try to reconcile
        if b.status == 'pending' and getattr(b, 'stripe_session_id', None) and stripe.api_key:
            try:
                sess = stripe.checkout.Session.retrieve(b.stripe_session_id)
                payment_status = sess.get('payment_status') or getattr(sess, 'payment_status', None)
                if payment_status == 'paid':
                    b.status = 'confirmed'
                    b.save()
            except Exception:
                # Non-fatal: leave booking as-is if Stripe lookup fails
                pass
    for b in bookings:
        can_cancel = False
        try:
            if b.status != 'cancelled' and b.date_from > today:
                can_cancel = True
        except Exception:
            can_cancel = False
        booking_entries.append({'booking': b, 'can_cancel': can_cancel})

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

    today = timezone.localdate()
    if request.method == 'POST':
        if booking.date_from > today and booking.status != 'cancelled':
            booking.status = 'cancelled'
            booking.save()
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