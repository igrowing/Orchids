#!/usr/bin/env python
from __future__ import unicode_literals

import orchid_app.sensors.anemometer as anemometer
import orchid_app.sensors.max44009 as light
import orchid_app.sensors.yf_201s as water
import orchid_app.sensors.mlx90614 as mlx
import orchid_app.sensors.bme280 as bme
import paho.mqtt.subscribe as subscribe
from datetime import datetime
from threading import Thread
from decimal import Decimal
import time
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils.six import python_2_unicode_compatible
from django.db import transaction
from django.conf import settings

#from orchid_app import models
from orchid_app.models import Sensors
from orchid_app.models import Actions

POLL_PERIOD = 600  # seconds = 10 minutes
POLL_PERIOD_MIN = POLL_PERIOD / 60  # minutes

def on_start(self):
    '''Shut down everything could be open.'''
    import orchid_app.actuators.latching_valves as valves
    import orchid_app.actuators.valve as relays

    rep = []
    a = Actions()
    a.date = datetime.now()
    try:
        valves.LatchingValve(1).set_status(0)
        rep.append('LatchingValve:water(1)')
        a.water = False
        valves.LatchingValve(2).set_status(0)
        rep.append('LatchingValve:mist(2)')
        a.mist = False
        relays.Relay(1).set_status(0)
        rep.append('Relay:fan(1)')
        a.fan = False
        relays.Relay(2).set_status(0)
        rep.append('Relay:light(2)')
        a.light = False

        os.system('logger orchid_runner: shut off all actuators: ' + ', '.join(rep))
        a.save()
    except Exception as e:
        os.system('logger orchid_runner: failed to shut off all actuators. OK with: ' + ', '.join(rep))
        self.stderr.write('On start: %s (%s)' % (e.message, type(e)))

    self.stdout.write('Shut off all actuators: ' + ', '.join(rep))
    self.stdout.write('Action Records: ' + repr(Actions.objects.count()))


def avg(l):
    '''Convert values of list from str to float if needed. Return average of the collected values.'''

    if not l:
        return 0.0

    pre = [float(i) for i in l]
    return round(sum(pre)/len(pre), 2)


class Command(BaseCommand):
    help = 'Polls sensors and writes data into the DB.'

    # def add_arguments(self, parser):
    #     parser.add_argument('poll_id', nargs='+', type=int)

    def handle(self, *args, **options):

        # Run measure and publishing of GPIO data in background.
        threads = [Thread(target=water.run),
                   Thread(target=anemometer.run),
                   ]
        for t in threads:
            t.setDaemon(True)
            t.start()

        os.system('logger orchid_runner has started')
        on_start(self)

        data = {'wind': [], 'water': [], 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
        ts = time.time()

        while True:
            if time.time() - ts < POLL_PERIOD:
                try:  # Catch sensor reading data, stay running
                    # Wait for MQTT data
                    topic = "shm/orchid/wind/last_min"
                    data['wind'].append(float(subscribe.simple(topic, keepalive=65, will={'topic': topic, 'payload': 0.0}).payload))
                    topic = "shm/orchid/water/last_min"
                    data['water'].append(float(subscribe.simple(topic, keepalive=65, will={'topic': topic, 'payload': 0.0}).payload))
                    # Read i2c sensors
                    a, b, c = bme.readBME280All()
                    data['t_amb'].append(a)
                    data['hpa'].append(b)
                    data['rh'].append(c)
                    data['t_obj'].append(mlx.Melexis().readObject1())
                    data['lux'].append(light.readLight())
                except Exception as e:
                    self.stderr.write('On read: %s (%s)' % (e.message, type(e)))
                    time.sleep(60)  # Wait 1 minute before retry.
            else:
                n = datetime.now()
                s = Sensors()
                s.date = n.replace(minute=n.minute / POLL_PERIOD_MIN * POLL_PERIOD_MIN, second=0, microsecond=0)  # reduce to poll period resolution
                # Data conditioning by model/DB requirements
                s.t_amb = Decimal('{:.1f}'.format(avg(data['t_amb'])))
                s.t_obj = Decimal('{:.1f}'.format(avg(data['t_obj'])))
                s.water = Decimal('{:.1f}'.format(avg(data['water'])))
                s.wind = Decimal('{:.1f}'.format(avg(data['wind'])))
                s.hpa = Decimal('{:.1f}'.format(avg(data['hpa'])))
                s.rh = int(avg(data['rh']))
                s.lux = int(avg(data['lux']))
                self.stdout.write(str(s))
                try:  # Catch sensor reading data, stay running
                    # Write data to the DB
                    s.save()
                    self.stdout.write('Sensor Records: ' + repr(Sensors.objects.count()))
                except Exception as e:
                    self.stderr.write('On write: %s (%s)' % (e.message, type(e)))
                    time.sleep(60)  # Wait 1 minute before retry.
                # Reset the data structure
                data = {'wind': [], 'water': [], 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
                ts = time.time()

            # Example of catch bad data
            # try:
            #     poll = Poll.objects.get(pk=poll_id)
            # except Poll.DoesNotExist:
            #     raise CommandError('Poll "%s" does not exist' % poll_id)
            # self.stdout.write(self.style.SUCCESS('Successfully closed poll "%s"' % poll_id))

