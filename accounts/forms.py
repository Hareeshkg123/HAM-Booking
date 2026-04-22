from django import forms
from . models import Profile
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username','email','password1','password2']

    def clean_email(self):
        """Ensure the provided email address is not already used by another user.

        This provides a clear, field-level validation error that will be shown
        inline in the signup form template.
        """
        email = self.cleaned_data.get('email')
        if email:
            # case-insensitive check
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('A user with that email already exists.')
        return email


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username','email','first_name','last_name']


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['image','phone_number','address']