from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from property.models import Category, Place, Property


class PublicKeyTemplateTests(TestCase):
    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_base_template_omits_google_maps_when_key_is_missing(self):
        response = self.client.get(reverse('home:contact_us'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'maps.googleapis.com/maps/api/js?key=')
        self.assertNotContains(response, 'js/google-map.js')

    @override_settings(GOOGLE_MAPS_API_KEY='browser-key-123')
    def test_base_template_renders_google_maps_from_settings(self):
        response = self.client.get(reverse('home:contact_us'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'maps.googleapis.com/maps/api/js?key=browser-key-123')
        self.assertContains(response, 'js/google-map.js')
        self.assertNotContains(response, 'AIza')


class HomeSearchTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='searchhost', password='secret123')
        self.place = Place.objects.create(
            name='Cairo',
            image=SimpleUploadedFile('place.jpg', b'place-image', content_type='image/jpeg'),
        )
        self.other_place = Place.objects.create(
            name='Luxor',
            image=SimpleUploadedFile('place-2.jpg', b'place-image-2', content_type='image/jpeg'),
        )
        self.category = Category.objects.create(name='Hotel', icon='hotel')
        self.matching_property = Property.objects.create(
            owner=owner,
            name='Nile View Hotel',
            image=SimpleUploadedFile('hotel.jpg', b'listing-image', content_type='image/jpeg'),
            price=120,
            description='Near the river',
            places=self.place,
            category=self.category,
        )
        Property.objects.create(
            owner=owner,
            name='Desert Camp',
            image=SimpleUploadedFile('camp.jpg', b'listing-image-2', content_type='image/jpeg'),
            price=90,
            description='Outside the city',
            places=self.other_place,
            category=self.category,
        )

    def test_home_search_without_query_params_returns_empty_page_instead_of_500(self):
        response = self.client.get(reverse('home:home_search'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['property_list'].paginator.count, 0)
        self.assertContains(response, 'No Result')

    def test_home_search_strips_whitespace_and_filters_with_single_parameter(self):
        response = self.client.get(reverse('home:home_search'), {'name': '  Nile  '})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['property_list']), [self.matching_property])
        self.assertContains(response, 'Nile View Hotel')
