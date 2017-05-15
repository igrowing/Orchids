#!/usr/bin/env python
from __future__ import unicode_literals

import os
import re
import time
from datetime import datetime, timedelta
from threading import Thread
from decimal import Decimal

import paho.mqtt.subscribe as subscribe
from django.core.management.base import BaseCommand

import orchid_app.sensors.anemometer as anemometer
import orchid_app.sensors.max44009 as light
import orchid_app.sensors.yf_201s as water
import orchid_app.sensors.mlx90614 as mlx
import orchid_app.sensors.bme280 as bme

import orchid_app.controller as controller
from orchid_app.models import Sensors, Actions

import warnings
warnings.filterwarnings('ignore')

POLL_PERIOD = 600  # seconds = 10 minutes
POLL_PERIOD_MIN = POLL_PERIOD / 60  # minutes
MAX_FLOW_RATE = 2.5  # L/minute.  This is threshold for emergency water leakage detection. If more than the threshold then close the valves.
MAX_LEAK_RATE = 0.008
MAX_SEND_COUNT = POLL_PERIOD / 10  # Send leakage message once in hour
send_counter = 0
water_trigger = False

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

        #######################################################################################
        ##################                 PREPARATIONS                ########################
        #######################################################################################

        os.system('logger orchid_runner has started')
        # Shut down on system start/restart everything could be open.
        controller.activate(reason='System startup', force=True, mist=False, drip=False, fan=False, light=False, heat=False)

        # Run measure and publishing of GPIO data in background.
        threads = [Thread(target=water.run),
                   Thread(target=anemometer.run),
                   Thread(target=controller.act_current_state),
                   ]
        for t in threads:
            t.setDaemon(True)
            t.start()

        # Keep preliminary data for averaging
        data = {'wind': [], 'water': 0.0, 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
        ts = time.time()

        #######################################################################################
        ##################                   MAIN LOOP                 ########################
        #######################################################################################

        while True:
            if time.time() - ts < POLL_PERIOD:
                #######################################################################################
                ##################     SHORT CYCLE ACTIONS, DATA AVERAGING     ########################
                #######################################################################################
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

                # Process timer
                try:
                    # Find last record with Timer enable
                    filt = {'reason__icontains': 'with timer'}
                    qs = Actions.objects.filter(**filt).last()

                    if 'with timer' in qs.reason.lower():
                        min_l = re.findall('(\d+) min', qs.reason.lower())
                        secs = int(min_l[0]) * 60 if min_l else 0
                        # Time gone. Check if needed action.
                        if (datetime.utcnow() - qs.date.replace(tzinfo=None)).total_seconds() > secs:
                            was_on = [k for k, v in qs.get_all_fields().iteritems() if v]
                            if was_on:
                                changed = False
                                # Avoid exception in case of empty database.
                                la = Actions.objects.last().get_all_fields()
                                for i in was_on:
                                    if la[i]:
                                        la[i] = False
                                        changed = True

                                if changed:
                                    self.stdout.write('Timer ended: %s' % datetime.now())
                                    self.stdout.flush()
                                    controller.activate(reason='Manual timer off', **la)

                except Exception as e:  # TODO: Narrowise the catch, it's too wide...
                    pass  # Till any action avaialble

            else:
                #######################################################################################
                ##################      LONG CYCLE ACTIONS, SD-CARD WRITE      ########################
                #######################################################################################
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
                # self.stdout.write(str(s))
                try:  # Catch sensor reading data, stay running
                    # Write data to the DB
                    s.save()
                    # self.stdout.write('Sensor Records: ' + repr(Sensors.objects.count()))
                except Exception as e:
                    self.stderr.write('On write: %s (%s)' % (e.message, type(e)))
                    time.sleep(60)  # Wait 1 minute before retry.
                # Reset the data structure
                data = {'wind': [], 'water': 0.0, 't_amb': [], 't_obj': [], 'hpa': [], 'rh': [], 'lux': []}
                ts = time.time()

                # Calculate current state
                controller.read_current_state()

            # Example of catch bad data
            # try:
            #     poll = Poll.objects.get(pk=poll_id)
            # except Poll.DoesNotExist:
            #     raise CommandError('Poll "%s" does not exist' % poll_id)
            # self.stdout.write(self.style.SUCCESS('Successfully closed poll "%s"' % poll_id))


def check_water_flow(liters):
    # Take emergency actions
    # Find out which valve is open
    la = controller.get_last_action()
    if la.mist or la.water and liters > MAX_FLOW_RATE:
            # Try to shut open valve off
            controller.activate(reason='Emergency shut off', force=True, mist=False, water=False,
                                fan=la.fan, light=la.light, heat=la.heat)

            # Build emergency message
            msg = 'Water leakage is detected in circuit(s): '
            msg += 'drip ' if la.water else ''
            msg += 'mist' if la.mist else ''
            msg += '\n%s liters of water ran in last minute when should be no more than %s liters/minute.\n' \
                   'Opened valve closed. This may impact watering and/or temperature conditions.\n' \
                   'Take actions immediately.' % (str(round(liters, 3)), str(MAX_FLOW_RATE))
            subj = 'Orchid farm emergency: water leakage detected'
            controller.send_message(subj, msg)

    # Check leakage when all valves closed
    elif liters > MAX_LEAK_RATE:
        global water_trigger
        if water_trigger:
            global send_counter
            if send_counter == 0:
                # Try to shut open valve off
                controller.activate(reason='Emergency shut off', force=True, mist=False, water=False,
                                    fan=la.fan, light=la.light, heat=la.heat)

                # Build emergency message
                msg = 'Water leakage is detected while all valves should be closed.'\
                      '\n%s liters of water leaked in last minute when should be 0.\n' \
                      'Tried to close all valves. This may impact watering and/or temperature conditions.\n' \
                      'Take actions immediately.' % str(round(liters, 3))
                subj = 'Orchid farm emergency: water leakage detected'
                controller.send_message(subj, msg)
                send_counter += 1
                water_trigger = False
            elif send_counter < MAX_SEND_COUNT:
                send_counter += 1
            else:
                send_counter = 0
        else:
            water_trigger = True
