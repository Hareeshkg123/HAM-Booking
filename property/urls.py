from django.urls import path
from .views import *
app_name = 'property'

urlpatterns = [
    path('',PropertyList.as_view(), name= 'property_list'),
    path('add/', AddListing.as_view(), name='property_add'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),
    path('<int:pk>/edit/', EditListing.as_view(), name='property_edit'),
    path('<int:pk>/delete/', DeleteListing.as_view(), name='property_delete'),
    path('<slug:slug>', PropertyDetail.as_view(), name='property_detail'),
]
