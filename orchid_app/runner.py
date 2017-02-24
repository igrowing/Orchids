#!/usr/bin/env python
from __future__ import unicode_literals

import sensors.anemometer as anemometer
import sensors.yf_201s as water
import sensors.max44009 as light
import sensors.mlx90614 as mlx
import sensors.bme280 as bme
import time
from threading import Thread

# from django.db import models
# from django.urls import reverse
from django.conf import settings
from django.utils.six import python_2_unicode_compatible
import paho.mqtt.subscribe as subscribe

from datetime import datetime
from models import Sensors

# Run measure and publishing of GPIO data in background.
threads = [Thread(target=anemometer.run),
           Thread(target=water.run),
           ]
[t.start for t in threads]

while True:
    t = datetime.now()
    # Read i2c sensors
    # Write data to the DB
    s = Sensors()
    s.date = datetime.now()  # reduce to minute resolution
    s.t_amb, s.hpa, s.rh = bme.readBME280All()
    s.t_obj = mlx.Melexis().readObject1()
    s.lux = light.readLight()
    s.water = subscribe.simple("shm/orchid/water/last_min").payload  # read from MQTT
    s.wind = subscribe.simple("shm/orchid/wind/last_min").payload
    s.save()
    delta = datetime.now() - t
    time.sleep(10 - delta.microseconds / 1000000.0)
    print Sensors.objects.count()
