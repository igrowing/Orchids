from __future__ import unicode_literals

from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils.six import python_2_unicode_compatible

from orchid_app import utils

@python_2_unicode_compatible
class Sensors(models.Model):
    date = models.DateTimeField(unique=True)
    t_amb = models.DecimalField(max_digits=4, decimal_places=1)
    t_obj = models.DecimalField(max_digits=4, decimal_places=1)
    rh = models.PositiveIntegerField()
    hpa = models.DecimalField(max_digits=5, decimal_places=1)
    lux = models.PositiveIntegerField()
    wind = models.DecimalField(max_digits=4, decimal_places=2)
    water = models.DecimalField(max_digits=4, decimal_places=2)

    def get_absolute_url(self):
        return reverse("sensors:detail", args=(self.id,))

    def __str__(self):
        return "[@{}] t_amb: {}, t_obj:{}, rh:{}, hpa:{}, lux:{}, water:{}, wind:{}".format(
            self.date,
            self.t_amb,
            self.t_obj,
            self.rh,
            self.hpa,
            self.lux,
            self.water,
            self.wind,
        )

    def get_all_fields(self, exclude=('id', 'date')):
        return get_all_fields(self, exclude=exclude)


@python_2_unicode_compatible
class Actions(models.Model):
    date = models.DateTimeField(unique=True)
    mist = models.BooleanField(default=False)
    fan = models.BooleanField(default=False)
    heat = models.BooleanField(default=False)
    water = models.BooleanField(default=False)
    light = models.BooleanField(default=False)
    reason = models.TextField(default='')

    def __str__(self):
        return "[@{}] mist:{} fan:{} water:{} light:{} heat:{} reason:{}".format(
            self.date,
            self.mist,
            self.fan,
            self.water,
            self.light,
            self.heat,
            self.reason,
        )

    def equals(self, action):
        return self.get_all_fields() == action

    def get_all_fields(self, exclude=('id', 'date', 'reason')):
        return get_all_fields(self, exclude=exclude)


def get_all_fields(obj, exclude=[]):
    '''Returns a Dict of all field names and values.
    Exclude non-meaningful fields.

    Inspired by shaker: stackoverflow.com/a/2226150/1472042'''

    fields = utils.Dict()
    # Correct user input for exclude parameter
    if not exclude:
        exclude = []

    for f in obj._meta.fields:
        fname = f.name
        # get value of the field
        try:
            value = getattr(obj, fname)
        except AttributeError:  # maybe use: obj.DoesNotExist ?
            value = None

        # only display fields with values and skip some fields entirely
        if f.editable and fname not in exclude:
            fields[fname] = value

    return fields


