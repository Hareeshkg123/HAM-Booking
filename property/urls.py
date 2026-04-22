from django.urls import path
from .views import *
app_name = 'property'

urlpatterns = [
    path('',PropertyList.as_view(), name= 'property_list'),
    path('add/', AddListing.as_view(), name='property_add'),
    path('<slug:slug>', PropertyDetail.as_view(), name='property_detail'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),
]
