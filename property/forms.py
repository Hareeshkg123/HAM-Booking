from django import forms 
from .models import *
from django.core.exceptions import ValidationError
from datetime import date

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
    class Meta:
        model = Property
        fields = ['name', 'image', 'price', 'description', 'places', 'category']
