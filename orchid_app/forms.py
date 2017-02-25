from django import forms
from django.forms.widgets import CheckboxSelectMultiple

from orchid_app import models


class ActionsForm(forms.Form):
    drip = forms.BooleanField(required=False)
    mist = forms.BooleanField(required=False)
    fan = forms.BooleanField(required=False)
    light = forms.BooleanField(required=False)
    heat = forms.BooleanField(required=False)

class OrchidForm(forms.ModelForm):

    # def __init__(self, user, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.fields['categories'].queryset = user.categories.all()


    class Meta:
        model = models.Sensors
        exclude = (
            'user',
        )


class FeebackForm(forms.Form):
    email = forms.EmailField()
    subject = forms.CharField()
    description = forms.CharField(widget=forms.Textarea())
    phone = forms.CharField(required=False)

