from django import forms 
from .models import *
from django.core.exceptions import ValidationError
from datetime import date


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        clean_one = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]

class PropertyBookForm(forms.ModelForm):
    class Meta:
        model = PropertyBook
        fields = ['date_from','date_to','guest','children']
        widgets = {
            'date_from': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'date_to': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get('date_from')
        date_to = cleaned.get('date_to')

        if date_from and date_to:
            # check that check-out is strictly after check-in
            if date_to <= date_from:
                self.add_error('date_to', ValidationError('Check-out must be after check-in.'))

        # optional: prevent booking in the past
        if date_from and date_from < date.today():
            self.add_error('date_from', ValidationError('Check-in cannot be in the past.'))

        return cleaned


class PropertyForm(forms.ModelForm):
    extra_images = MultipleFileField(
        required=False,
        help_text='Upload up to 9 extra images. Each listing can have a maximum of 10 images in total.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        self.fields['extra_images'].required = False
        self.fields['price'].widget.attrs['min'] = 1
        existing_extra = self.instance.property_image.count() if self.instance.pk else 0
        self.fields['extra_images'].help_text = (
            f'Upload extra gallery images. This listing can have up to 10 images total. '
            f'Current extra images: {existing_extra}.'
        )

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise ValidationError('Price must be greater than 0.')
        return price

    def clean(self):
        cleaned_data = super().clean()
        extra_images = cleaned_data.get('extra_images', [])
        existing_extra = self.instance.property_image.count() if self.instance.pk else 0
        main_image_count = 1 if (self.instance.pk or cleaned_data.get('image')) else 0
        total_images = main_image_count + existing_extra + len(extra_images)

        if total_images > 10:
            self.add_error(
                'extra_images',
                ValidationError('A listing can have a maximum of 10 images in total.'),
            )

        return cleaned_data

    def save_gallery_images(self, property_obj):
        for image in self.cleaned_data.get('extra_images', []):
            PropertyImages.objects.create(property=property_obj, image=image)

    class Meta:
        model = Property
        fields = ['name', 'image', 'price', 'description', 'places', 'category']
