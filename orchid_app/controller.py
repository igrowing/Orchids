import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from orchid_app import actuators, utils, models
from orchid_app.utils import sendmail as sendmail, pushb

MIN_AVG_HOURS = 0.4  # TODO: reconsider the value

# state_name = {'action_name': [off_period_min, on_period_min, exclusion], ...}
#emergency_low = {'water': [20130, 30], 'mist': [,], 'vent': [,], 'ac': [,], 'heat': [,], 'shade': [,], 'fertilize': [,]}
act_dict = {
    't0h0w0': {'heat': [60, 0]},
    't6h0w0': {'mist': [60, 10200]},  # Mist for 1 hour in a week.
    't6h40w0': {'water': [30, 20130]},  # Water for 30 min in 2 weeks.
    't6h80w0': {'water': [15, 20145]},  # Water for 15 min in 2 weeks.
    't17h0w0': {'water': [30, 10230], 'mist': [60, 2820]},  # Water for 30 min in 1 week. Mist for 1 hour every 2 days.
    't17h40w0': {'water': [30, 10230]},  # Water for 30 min in 1 week.
    't25h0w0': {'water': [30, 10230], 'mist': [30, 1410, 'vent'], 'vent': [60, 1380, 'mist']},  # Water for 30 min in 1 week. Mist for 30 minutes every day at the most light. Interleave mist with vent for 1 hour.
    't25h0w5': {'water': [30, 10230], 'mist': [30, 1410]},  # Water for 30 min in 1 week. Mist for 30 minutes every day.
    't25h40w0': {'water': [30, 10230], 'mist': [5, 1435, 'vent'], 'vent': [60, 1380, 'mist']},  # Water for 30 min in 1 week. Mist for 5 minutes every day at the most light. Interleave mist with vent for 1 hour.
    't25h40w5': {'water': [30, 10230], 'mist': [5, 1435]},  # Water for 30 min in 1 week. Mist for 5 minutes every day.
    't25h80w0': {'water': [30, 10230], 'vent': [60, 1380]},  # Water for 30 min in 1 week. Vent for 1 hour at the most light and no wind.
    't25h80w5': {'water': [30, 10230]},  # Water for 30 min in 1 week.
    't28h0w0': {'water': [30, 10230], 'mist': [30, 90, 'vent'], 'vent': [60, 60, 'mist']},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light. Interleave mist with vent for 1 hour.
    't28h0w5': {'water': [30, 10230], 'mist': [30, 90]},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light.
    't28h80w0': {'water': [30, 10230], 'vent': [30, 90]},  # Water for 30 min in 1 week. Vent for 30 minutes at the most light and no wind.
    't28h80w5': {'water': [30, 10230]},  # Water for 30 min in 1 week.
    't36h0w0': {'mist': [30, 30, 'vent'], 'vent': [30, 30, 'mist'], 'ac': [60, 0], 'shade': [400, 0]}, # When t_amb > 36 or t_obj > 25
}

state_list = [
    {'name': 't0h0w0', 'avg': MIN_AVG_HOURS,  # Don't average, emergency state.
     'criteria': {'tmin': 0, 'tmax': 6, 'hmin': 0, 'hmax': 100, 'wmin': 0, 'wmax': 100},
     'action': {'heat': [60, 0]}},
    {'name': 't6h0w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 100},
     'action': {'mist': [60, 10200]}},  # Mist for 1 hour in a week.
    {'name': 't6h40w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 40, 'hmax': 80, 'wmin': 0, 'wmax': 100},
     'action': {'water': [30, 20130]}},  # Water for 30 min in 2 weeks.
    {'name': 't6h80w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 80, 'hmax': 100, 'wmin': 0, 'wmax': 100},
     'action': {'water': [15, 20145]}},  # Water for 15 min in 2 weeks.
    {'name': 't17h0w0', 'avg': 12,
     'criteria': {'tmin': 17, 'tmax': 25, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 100},
     'action': {'water': [30, 10230], 'mist': [60, 2820]}},  # Water for 30 min in 1 week. Mist for 1 hour every 2 days.
    {'name': 't17h40w0', 'avg': 12,
     'criteria': {'tmin': 17, 'tmax': 25, 'hmin': 40, 'hmax': 100, 'wmin': 0, 'wmax': 100},
     'action': {'water': [30, 10230]}},  # Water for 30 min in 1 week.
    {'name': 't25h0w0', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 5},
     'action': {'water': [30, 10230], 'mist': [30, 1410, 'vent'], 'vent': [60, 1380, 'mist']}},  # Water for 30 min in 1 week. Mist for 30 minutes every day at the most light. Interleave mist with vent for 1 hour.
    {'name': 't25h0w5', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 0, 'hmax': 40, 'wmin': 5, 'wmax': 100},
     'action': {'water': [30, 10230], 'mist': [30, 1410]}},  # Water for 30 min in 1 week. Mist for 30 minutes every day.
    {'name': 't25h40w0', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 40, 'hmax': 80, 'wmin': 0, 'wmax': 5},
     'action': {'water': [30, 10230], 'mist': [5, 1435, 'vent'], 'vent': [60, 1380, 'mist']}},  # Water for 30 min in 1 week. Mist for 5 minutes every day at the most light. Interleave mist with vent for 1 hour.
    {'name': 't25h40w5', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 40, 'hmax': 80, 'wmin': 5, 'wmax': 100},
     'action': {'water': [30, 10230], 'mist': [5, 1435]}},  # Water for 30 min in 1 week. Mist for 5 minutes every day.
    {'name': 't25h80w0', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 80, 'hmax': 100, 'wmin': 0, 'wmax': 5},
     'action': {'water': [30, 10230], 'vent': [60, 1380]}},  # Water for 30 min in 1 week. Vent for 1 hour at the most light and no wind.
    {'name': 't25h80w5', 'avg': 12,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 80, 'hmax': 100, 'wmin': 5, 'wmax': 100},
     'action': {'water': [30, 10230]}},  # Water for 30 min in 1 week.
    {'name': 't28h0w0', 'avg': 6,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 0, 'hmax': 80, 'wmin': 0, 'wmax': 5},
     'action': {'water': [30, 10230], 'mist': [30, 90, 'vent'], 'vent': [60, 60, 'mist']}},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light. Interleave mist with vent for 1 hour.
    {'name': 't28h0w5', 'avg': 6,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 0, 'hmax': 80, 'wmin': 5, 'wmax': 100},
     'action': {'water': [30, 10230], 'mist': [30, 90]}},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light.
    {'name': 't28h80w0', 'avg': 6,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 80, 'hmax': 100, 'wmin': 0, 'wmax': 5},
     'action': {'water': [30, 10230], 'vent': [30, 90]}},  # Water for 30 min in 1 week. Vent for 30 minutes at the most light and no wind.
    {'name': 't28h80w5', 'avg': 6,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 80, 'hmax': 100, 'wmin': 5, 'wmax': 100},
     'action': {'water': [30, 10230]}},  # Water for 30 min in 1 week.
    {'name': 't36h0w0', 'avg': MIN_AVG_HOURS,  # Don't average, emergency state.
     'criteria': {'tmin': 36, 'tmax': 100, 'hmin': 0, 'hmax': 100, 'wmin': 0, 'wmax': 100},
     'action': {'mist': [30, 30, 'vent'], 'vent': [30, 30, 'mist'], 'ac': [60, 0], 'shade': [400, 0]}}, # When t_amb > 36 or t_obj > 25
]

# Global variable to minimize page loading time.
current_state = []

class State(object):
    # Class variables
    t = h = w = 0           # Temperature, humidity, wind are state definition.
    enter_datetime = None   # When the state was entered last time.
    action_datetime = None  # When action in this state was taken last time.
    action_dict = None

    def __init__(self, t, h, w, action_dict):
        self.t = t
        self.h = h
        self.w = w
        self.action_dict = action_dict

    def __str__(self):
        return 't{}h{}w{}: {}'.format(self.t, self.h, self.w, self.action_dict)

    def __repr__(self):
        return self.__str__()

    # Class functions
    def enter(self):
        self.enter_datetime = datetime.now()

    def is_valid(self, t, h, w, next_state=None):
        '''Returns True when t, h, w are greater than this state definition and less than next state provided.
        If no state provided then no maximum value checked.'''

        if next_state:
            return self.t <= t <= next_state.t and self.h <= h <= next_state.h and self.w <= w <= next_state.w
        else:
            return self.t <= t and self.h <= h and self.w <= w


def activate(reason='unknown', force=False, **kwargs):
    '''Internal function. Control the actuators.

    @:param kwargs: actuator_name=required_state. Can be boolean or string (on, off, value).
    @:returns string: message what was activated and deactivated.
    '''

    msg = []
    a = models.Actions()
    a.date = datetime.now()
    a.water = a.mist = a.fan = a.light = a.heat = False
    a.reason = reason

    la = get_last_action()

    for k, v in kwargs.iteritems():
        if type(v) == unicode:
            if v.lower() in ['on', 'true', 'enable', 'start']:
                v = True
            elif v.lower() in ['off', 'false', 'disable', 'stop']:
                v = False
        # Else: keep v as is

        msg.append(k + ': ' + str(v))
        if k == 'mist':
            if la.mist != v:
                actuators.LatchingValve(1).set_status(v)
            a.mist = v
        elif k == 'drip':
            if la.water != v:
                actuators.LatchingValve(2).set_status(v)
            a.water = v
        elif k == 'fan':
            if la.fan != v:
                actuators.Relay(1).set_status(v)
            a.fan = v
        elif k == 'light':
            if la.light != v:
                actuators.Relay(2).set_status(v)
            a.light = v
        elif k == 'heat':
            # Do something :)
            a.heat = v
        else:
            msg[-1] += "<<--Wrong action!"

    if not a.equals(la) or force:
        try:
            a.save()
        except Exception as e:
            sys.stderr.write('On start: %s (%s)' % (e.message, type(e)))
    else:
        msg.append('No changes. Skip action')

    msg.append('reason: ' + reason)
    return ', '.join(msg)


def get_last_action():
    res = utils.Dict()
    a = {}
    try:
        # Use 'if-else' dirty trick to avoid exception in case of empty database.
        a = models.Actions.objects.all().last()
    except Exception as e:
        sys.stderr.write('%s -- On start: %s (%s)' % (a, e.message, type(e)))

    # Use 'if-else' dirty trick to avoid exception in case of empty database.
    res.mist = getattr(a, 'mist', False)
    res.water = a.water if a else False
    res.fan = a.fan if a else False
    res.light = a.light if a else False
    res.heat = a.heat if a else False

    return res


def get_current_state():
    if not current_state:
        read_current_state()
    return current_state


def read_current_state():
    '''Calculate averages for all possible states. Choose the most appropriate state.
    Return status as full record of state_list and its index.'''

    status = calc_avg(MIN_AVG_HOURS)

    for i in range(len(state_list)):
        duration = state_list[i]['avg']
        # Skip repeating status calculation
        if status['duration'] != duration:
            status = calc_avg(duration)
            status['duration'] = duration

        cr = state_list[i]['criteria']
        if cr['tmin'] <= status['t_amb'] < cr['tmax'] and cr['hmin'] <= status['rh'] < cr['hmax'] and cr['wmin'] <= status['wind'] < cr['wmax']:
            global current_state
            current_state = (state_list[i], i)
            break


def calc_avg(duration):

    # Acquire relevant range of the data from the DB.
    ml = models.Sensors.objects.filter(date__gte=datetime.now() - timedelta(hours=duration)).values('wind', 'hpa', 't_amb', 't_obj', 'rh', 'lux')
    ed = defaultdict(int)  # Allow automatic adding of key is the key is not present in the dict.
    ed['duration'] = duration

    # Return empty dictionary if no records found (new database).
    if ml.count() == 0:
        return ed

    # Sum all values for each parameter.
    for d in ml:
        for k, v in d.iteritems():
            ed[k] += v

    # Calc the avg
    for k, v in ed.iteritems():
        ed[k] = ed[k] / ml.count()

    return ed


def send_message(subj, msg):
    # Send emergency mail
    sendmail.sendmail(subj, msg)
    # Send emergency IM
    pushb.send_note(subj, msg)

