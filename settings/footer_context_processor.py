from django.conf import settings as django_settings

from .models import Settings


def myfooter(request):
    myfooter = Settings.objects.last()
    return {
        'myfooter': myfooter,
        'GOOGLE_MAPS_API_KEY': getattr(django_settings, 'GOOGLE_MAPS_API_KEY', ''),
    }

    
