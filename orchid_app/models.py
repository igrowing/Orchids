from __future__ import unicode_literals

from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils.six import python_2_unicode_compatible


@python_2_unicode_compatible
class Sensors(models.Model):
    date = models.DateField(unique_for_date=True)
    t_amb = models.DecimalField(max_digits=2, decimal_places=2)
    t_obj = models.DecimalField(max_digits=2, decimal_places=2)
    rh = models.PositiveIntegerField()
    hpa = models.DecimalField(max_digits=4, decimal_places=1)
    lux = models.PositiveIntegerField()
    wind = models.DecimalField(max_digits=3, decimal_places=2)
    water = models.DecimalField(max_digits=3, decimal_places=2)

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


@python_2_unicode_compatible
class Actions(models.Model):
    date = models.DateField(unique_for_date=True)
    mist = models.BooleanField(default=False)
    fan = models.BooleanField(default=False)
    heat = models.BooleanField(default=False)
    water = models.BooleanField(default=False)
    light = models.BooleanField(default=False)

    def __str__(self):
        return "[@{}] mist{} fan{} water{} heat{}".format(
            self.date,
            self.mist,
            self.fan,
            self.water,
            self.heat,
        )

