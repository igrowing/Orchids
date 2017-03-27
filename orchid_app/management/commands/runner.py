#!/usr/bin/env python
from __future__ import unicode_literals

import orchid_app.sensors.anemometer as anemometer
import orchid_app.sensors.max44009 as light
import orchid_app.sensors.yf_201s as water
import orchid_app.sensors.mlx90614 as mlx
import orchid_app.sensors.bme280 as bme
import paho.mqtt.subscribe as subscribe
import orchid_app.views as views
from datetime import datetime
from threading import Thread
from decimal import Decimal
import orchid_app.utils.sendmail as sendmail
import orchid_app.utils.pushb as pushb

import time
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils.six import python_2_unicode_compatible
from django.db import transaction
from django.conf import settings

from orchid_app.models import Sensors
from orchid_app.models import Actions

POLL_PERIOD = 600  # seconds = 10 minutes
POLL_PERIOD_MIN = POLL_PERIOD / 60  # minutes
MAX_FLOW_RATE = 2.0  # L/minute.  This is threshold for emergency water leakage detection. If more than the threshold then close the valves.


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
        # Shut down on system start/restart everything could be open.
        views._activate(reason='System startup', mist=False, drip=False, fan=False, light=False, heat=False)

        # Keep preliminary data for averaging
        data = {'wind': [], 'water': 0.0, 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
        ts = time.time()

        while True:
            if time.time() - ts < POLL_PERIOD:
                try:  # Catch sensor reading data, stay running
                    # Wait for MQTT data
                    topic = "shm/orchid/wind/last_min"
                    data['wind'].append(float(subscribe.simple(topic, keepalive=65, will={'topic': topic, 'payload': 0.0}).payload))
                    topic = "shm/orchid/water/last_min"
                    last_water = float(subscribe.simple(topic, keepalive=65, will={'topic': topic, 'payload': 0.0}).payload)
                    check_water_flow(last_water)
                    data['water'] += last_water
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
                s.water = Decimal('{:.1f}'.format(data['water']))
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
                data = {'wind': [], 'water': 0.0, 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
                ts = time.time()

            # Example of catch bad data
            # try:
            #     poll = Poll.objects.get(pk=poll_id)
            # except Poll.DoesNotExist:
            #     raise CommandError('Poll "%s" does not exist' % poll_id)
            # self.stdout.write(self.style.SUCCESS('Successfully closed poll "%s"' % poll_id))

def check_water_flow(liters):
    if liters < MAX_FLOW_RATE:
        return

    # Take emergency actions
    # Find out which valve is open
    la = views._get_last_action()
    # Try to shut open valve off
    views._activate(reason='Emergency shut off', mist=False if la.mist else True, drip=False if la.water else True,
                    fan=la.fan, light=la.light, heat=la.heat)

    # Build emergency message
    msg = 'Water leakage is detected in circuit(s): '
    msg += 'drip ' if la.water else ''
    msg += 'mist' if la.mist else ''
    msg += '\nOpened valve closed. This may impact watering and/or temperature conditions.\nTake actions immediately.'
    subj = 'Orchid farm emergency: water leakage detected'

    # Send emergency mail
    sendmail.sendmail(subj, msg)
    # Send emergency IM
    pushb.send_note(subj, msg)
