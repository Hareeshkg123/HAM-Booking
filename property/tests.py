from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.datastructures import MultiValueDict

from accounts.models import Profile
from property.forms import PropertyBookForm, PropertyForm
from property.models import Category, Place, Property, PropertyImages


class HostListingManagementTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username='host', password='secret123')
        self.other_host = User.objects.create_user(username='otherhost', password='secret123')
        Profile.objects.filter(user=self.host).update(is_host=True)
        Profile.objects.filter(user=self.other_host).update(is_host=True)

        self.place = Place.objects.create(
            name='Cairo',
            image=SimpleUploadedFile('place.jpg', b'place-image', content_type='image/jpeg'),
        )
        self.category = Category.objects.create(name='Apartment', icon='home')
        self.property = Property.objects.create(
            owner=self.host,
            name='Original Name',
            image=SimpleUploadedFile('listing.jpg', b'listing-image', content_type='image/jpeg'),
            price=100,
            description='Original description',
            places=self.place,
            category=self.category,
        )
        self.duplicate_slug_property = Property.objects.create(
            owner=self.other_host,
            name='Original Name',
            image=SimpleUploadedFile('listing-2.jpg', b'listing-image-2', content_type='image/jpeg'),
            price=150,
            description='Second listing with same slug',
            places=self.place,
            category=self.category,
        )

    def make_image(self, name):
        return SimpleUploadedFile(name, b'image-bytes', content_type='image/jpeg')

    def test_owner_can_open_edit_form_with_existing_data(self):
        self.client.login(username='host', password='secret123')

        response = self.client.get(reverse('property:property_edit', args=[self.property.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Original Name"')
        self.assertContains(response, 'Original description')
        self.assertEqual(response.context['form'].instance, self.property)

    def test_owner_can_update_all_listing_fields_including_photo(self):
        self.client.login(username='host', password='secret123')
        edit_url = reverse('property:property_edit', args=[self.property.id])
        new_image = SimpleUploadedFile('updated.jpg', b'updated-image', content_type='image/jpeg')

        response = self.client.post(
            edit_url,
            {
                'name': 'Updated Name',
                'image': new_image,
                'price': 180,
                'description': 'Updated description',
                'places': self.place.id,
                'category': self.category.id,
            },
        )

        self.assertRedirects(response, reverse('accounts:mylisting'))
        self.property.refresh_from_db()
        self.assertEqual(self.property.name, 'Updated Name')
        self.assertEqual(self.property.price, 180)
        self.assertEqual(self.property.description, 'Updated description')
        self.assertTrue(self.property.image.name.endswith('updated.jpg'))

    def test_non_owner_cannot_edit_or_delete_listing(self):
        self.client.login(username='otherhost', password='secret123')

        edit_response = self.client.get(reverse('property:property_edit', args=[self.property.id]))
        delete_response = self.client.post(reverse('property:property_delete', args=[self.property.id]))

        self.assertRedirects(edit_response, reverse('accounts:mylisting'))
        self.assertRedirects(delete_response, reverse('accounts:mylisting'))
        self.assertTrue(Property.objects.filter(id=self.property.id).exists())

    def test_delete_confirmation_page_and_removal_from_home_page(self):
        self.client.login(username='host', password='secret123')
        delete_url = reverse('property:property_delete', args=[self.property.id])

        confirm_response = self.client.get(delete_url)
        delete_response = self.client.post(delete_url)
        home_response = self.client.get(reverse('property:property_list'))

        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, 'Delete Listing')
        self.assertContains(confirm_response, 'Yes, delete listing')
        self.assertRedirects(delete_response, reverse('accounts:mylisting'))
        self.assertFalse(Property.objects.filter(id=self.property.id).exists())
        self.assertNotContains(home_response, 'Original Name')

    def test_delete_works_even_when_another_listing_has_same_slug(self):
        self.client.login(username='host', password='secret123')

        response = self.client.post(reverse('property:property_delete', args=[self.property.id]))

        self.assertRedirects(response, reverse('accounts:mylisting'))
        self.assertFalse(Property.objects.filter(id=self.property.id).exists())
        self.assertTrue(Property.objects.filter(id=self.duplicate_slug_property.id).exists())

    def test_property_form_requires_all_listing_fields(self):
        form = PropertyForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('image', form.errors)
        self.assertIn('price', form.errors)
        self.assertIn('description', form.errors)
        self.assertIn('places', form.errors)
        self.assertIn('category', form.errors)

    def test_property_form_rejects_zero_and_negative_price(self):
        zero_price_form = PropertyForm(
            data={
                'name': 'Zero Price Listing',
                'price': 0,
                'description': 'Test description',
                'places': self.place.id,
                'category': self.category.id,
            }
        )
        negative_price_form = PropertyForm(
            data={
                'name': 'Negative Price Listing',
                'price': -50,
                'description': 'Test description',
                'places': self.place.id,
                'category': self.category.id,
            }
        )

        self.assertFalse(zero_price_form.is_valid())
        self.assertFalse(negative_price_form.is_valid())
        self.assertIn('price', zero_price_form.errors)
        self.assertIn('price', negative_price_form.errors)

    def test_booking_form_children_choices_include_zero(self):
        form = PropertyBookForm()

        self.assertIn((0, '0'), form.fields['children'].choices)
        self.assertNotIn((0, '0'), form.fields['guest'].choices)

    def test_property_form_allows_up_to_ten_total_images(self):
        form = PropertyForm(
            data={
                'name': 'Gallery Listing',
                'price': 200,
                'description': 'Has gallery images',
                'places': self.place.id,
                'category': self.category.id,
            },
            files=MultiValueDict(
                {
                    'image': [self.make_image('main.jpg')],
                    'extra_images': [self.make_image(f'extra-{index}.jpg') for index in range(9)],
                }
            ),
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_property_form_rejects_more_than_ten_total_images(self):
        form = PropertyForm(
            data={
                'name': 'Too Many Images',
                'price': 220,
                'description': 'Too many uploads',
                'places': self.place.id,
                'category': self.category.id,
            },
            files=MultiValueDict(
                {
                    'image': [self.make_image('main.jpg')],
                    'extra_images': [self.make_image(f'extra-{index}.jpg') for index in range(10)],
                }
            ),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('extra_images', form.errors)

    def test_edit_form_rejects_extra_images_above_total_limit(self):
        for index in range(8):
            PropertyImages.objects.create(
                property=self.property,
                image=self.make_image(f'existing-{index}.jpg'),
            )

        form = PropertyForm(
            data={
                'name': self.property.name,
                'price': self.property.price,
                'description': self.property.description,
                'places': self.place.id,
                'category': self.category.id,
            },
            files=MultiValueDict(
                {
                    'image': [self.make_image('replacement.jpg')],
                    'extra_images': [self.make_image('new-1.jpg'), self.make_image('new-2.jpg')],
                }
            ),
            instance=self.property,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('extra_images', form.errors)


class PropertyDetailSanitizationTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username='host2', password='secret123')
        self.place = Place.objects.create(
            name='Alexandria',
            image=SimpleUploadedFile('place-2.jpg', b'place-image', content_type='image/jpeg'),
        )
        self.category = Category.objects.create(name='Villa', icon='villa')
        self.property = Property.objects.create(
            owner=self.host,
            name='Sea View Villa',
            image=SimpleUploadedFile('villa.jpg', b'listing-image', content_type='image/jpeg'),
            price=250,
            description=(
                '<p>Roomy <strong>sea-view</strong> stay.</p>'
                '<script>xss-property-script</script>'
                '<img src="x" onerror="xss-property-image">'
            ),
            places=self.place,
            category=self.category,
        )

    def test_property_detail_sanitizes_stored_description(self):
        response = self.client.get(reverse('property:property_detail', args=[self.property.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<strong>sea-view</strong>', html=False)
        self.assertNotContains(response, 'xss-property-script')
        self.assertNotContains(response, 'onerror=')
