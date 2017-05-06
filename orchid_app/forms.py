from django import forms
from django.forms.widgets import CheckboxSelectMultiple

from orchid_app import models


class ActionsForm(forms.Form):
    water = forms.BooleanField(required=False, help_text='Dripping system')
    mist = forms.BooleanField(required=False, help_text='Increases humidity, lowers temperature')
    fan = forms.BooleanField(required=False, help_text='Moves air, lowers temperature')
    light = forms.BooleanField(required=False, help_text='Photosynthesis makes food for plants')
    heat = forms.BooleanField(required=False, help_text='Anti-freezing system')
    time = forms.IntegerField(min_value=0, max_value=999, required=False, help_text="Shut off after X in minutes (0 - don't shut off)",
                              initial=0, disabled=False)

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

