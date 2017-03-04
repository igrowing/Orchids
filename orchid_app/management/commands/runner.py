#!/usr/bin/env python
from __future__ import unicode_literals

import orchid_app.sensors.anemometer as anemometer
import orchid_app.sensors.yf_201s as water
import orchid_app.sensors.max44009 as light
import orchid_app.sensors.mlx90614 as mlx
import orchid_app.sensors.bme280 as bme
import time
from threading import Thread

from decimal import Decimal
#from django.template.defaultfilters import floatformat
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from orchid_app import models
from orchid_app.models import Sensors

# from django.db import models
# from django.urls import reverse
from django.conf import settings
from django.utils.six import python_2_unicode_compatible
import paho.mqtt.subscribe as subscribe

from datetime import datetime


POLL_PERIOD = 600  # seconds = 10 minutes
POLL_PERIOD_MIN = POLL_PERIOD / 60  # minutes

water_data = []
wind_data = []


def runWater():
    water.run()
    t = time.time()
    while True:
        water_data = (subscribe.simple("shm/orchid/water/last_min").payload, time.time() - t < 120)
        t = time.time()
        print 'Water:', water_data


def runWind():
    anemometer.run()
    t = time.time()
    while True:
        wind_data = (subscribe.simple("shm/orchid/wind/last_min").payload, time.time() - t < 120)
        t = time.time()
        print 'Wind:', wind_data

def get_payload(client, userdata, message):
    return message.payload

class Command(BaseCommand):
    help = 'Polls sensors and writes data into the DB.'

    # def add_arguments(self, parser):
    #     parser.add_argument('poll_id', nargs='+', type=int)

    def handle(self, *args, **options):

        # Run measure and publishing of GPIO data in background.
        # threads = [Thread(target=anemometer.run),
        #            Thread(target=water.run),
        #            ]
        threads = [Thread(target=runWater),
                   Thread(target=runWind),
                   ]
        for t in threads:
            t.setDaemon(True)
            t.start()

        while True:
            t = time.time()
            # Read i2c sensors
            s = Sensors()
            n = datetime.now()
            s.date = n.replace(minute=n.minute / POLL_PERIOD_MIN * POLL_PERIOD_MIN, second=0, microsecond=0)  # reduce to poll period resolution
            s.t_amb, s.hpa, s.rh = bme.readBME280All()
            s.t_obj = mlx.Melexis().readObject1()
            s.lux = light.readLight()
            self.stdout.write("Start handle")
            # s.water = subscribe.callback(get_payload, "shm/orchid/water/last_min")  # read from MQTT
            # self.stdout.write("Start ha")
            # s.wind = subscribe.callback(get_payload, "shm/orchid/wind/last_min")
            # s.water = subscribe.simple("shm/orchid/water/last_min").payload  # read from MQTT
            # s.wind = subscribe.simple("shm/orchid/wind/last_min").payload
            s.water = water_data[0] if water_data else 0.0
            s.wind = wind_data[0] if wind_data else 0.0

            import decimal
            decimal.getcontext().prec = 1
            self.stdout.write("Start postprocess" + str(water_data + wind_data))
            # Data conditioning by model/DB requirements
            s.t_amb = Decimal('{:.1f}'.format(s.t_amb))
            s.t_obj = Decimal('{:.1f}'.format(s.t_obj))
            s.water = Decimal('{:.1f}'.format(s.water))
            s.wind = Decimal('{:.1f}'.format(s.wind))
            s.hpa = Decimal('{:.1f}'.format(s.hpa))
            s.rh = int(s.rh)
            s.lux = int(s.lux)
            self.stdout.write(str(s))

            # Write data to the DB
            s.save()
            self.stdout.write('Redords: ' + repr(Sensors.objects.count()))
            dt = 1.0 * POLL_PERIOD - (time.time() - t)
            self.stdout.write("Sleeping... " + str(dt) + str(water_data))
            time.sleep(dt)

            # Example of catch bad data
            # try:
            #     poll = Poll.objects.get(pk=poll_id)
            # except Poll.DoesNotExist:
            #     raise CommandError('Poll "%s" does not exist' % poll_id)
            # self.stdout.write(self.style.SUCCESS('Successfully closed poll "%s"' % poll_id))

