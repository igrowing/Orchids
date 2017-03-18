#!/usr/bin/env python
from __future__ import unicode_literals

import sensors.anemometer as anemometer
import sensors.yf_201s as water
import sensors.max44009 as light
import sensors.mlx90614 as mlx
import sensors.bme280 as bme
import time
from threading import Thread

# Load Django to write the data into the tables
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'orchid_app.settings'
import django
django.setup()

# from django.db import models
# from django.urls import reverse
from django.conf import settings
from django.utils.six import python_2_unicode_compatible
import paho.mqtt.subscribe as subscribe

from datetime import datetime
from models import Sensors

wa = []
wi = []


def collect_water():
    while True:
        wa.append(subscribe.simple("shm/orchid/water/last_min").payload)  # read from MQTT


def collect_wind():
    while True:
        wa.append(subscribe.simple("shm/orchid/wind/last_min").payload)  # read from MQTT


def avg_water():
    '''Average the collected values, clean the array, return the average.'''
    global wa
    pre = [float(i) for i in wa]
    wa = []
    return round(sum(pre)/len(pre), 2)


def avg_wind():
    global wi
    pre = [float(i) for i in wi]
    wi = []
    return round(sum(pre)/len(pre), 2)

# Run measure and publishing of GPIO data in background.
threads = [Thread(target=anemometer.run),
           Thread(target=water.run),
           Thread(target=collect_water),
           Thread(target=collect_wind),
           ]
[t.start for t in threads]

while True:
    # TODO: fix the loop. The bug is:
    # Data is acquired every 10 minutes. Wind and water are posting data every minute and every second.
    # I.e. 9 of 10 measures are lost. Make them average.

    t = datetime.now()
    # Read i2c sensors
    # Write data to the DB
    s = Sensors()
    s.date = datetime.now()  # reduce to minute resolution
    s.t_amb, s.hpa, s.rh = bme.readBME280All()
    s.t_obj = mlx.Melexis().readObject1()
    s.lux = light.readLight()
    # s.water = subscribe.simple("shm/orchid/water/last_min").payload  # read from MQTT
    s.water = avg_water()
    # s.wind = subscribe.simple("shm/orchid/wind/last_min").payload
    s.wind = avg_wind()
    s.save()
    print Sensors.objects.count(), s
    delta = datetime.now() - t
    time.sleep(10 - delta.microseconds / 1000000.0)  # wait up to 10 minutes
