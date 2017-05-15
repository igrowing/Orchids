import sys
import time
import copy
from django.core import exceptions
from collections import defaultdict
from datetime import datetime, timedelta

from orchid_app import actuators, models
from orchid_app.utils import sendmail, pushb

MIN_AVG_HOURS = 0.4   # TODO: reconsider the value
MAX_TIMEOUT = 999999  # Very long time indicated no action was found
NO_DATA = -1

# Global variables:
#  Minimize page loading time.
current_state = []

# Primitive action description:
# 'water', dripping watering. can be on/off.
# 'mist',  water mist. can be on/off.
# 'fan',   Fan/ventilation. can be on/off.
# 'heat',  heater (separated power supply!). can be on/off.
# 'ac',    Air conditioner. can be on/off. TBD: add sophisticated control.
# 'shade', Rolling or twisting shade. can be on/off.
# 'light', Lamps or other lighting. can be on/off.
PRIM_ACTIONS = ['water', 'mist', 'fan', 'heat', 'light']  # 'mix' is not in primitive actions. Mix must be parsed separately.
#PRIM_ACTIONS = ['water', 'mist', 'fan', 'heat', 'ac', 'shade', 'light']
# Mix actions define just order of activity, i.e. priority. The structure is the same [on_time, off_time].
# Example: 'mix': {'mist': [5, 40], 'fan': [10, 35]}
# means: Turn mist on for 5 minutes, then turn mist off anf turn fan on for 10 min, then turn fan off for 30 min and repeat.
# In this example full cycle time is 45 min: mist on 5min + fan on 10min + off 30min.
# I.e. sum of on+off time for each actuator = full cycle time. 5+40=45, 10+35=45.
MIX_ORDER = ['mist', 'fan']  # Define action priority in mix.

state_list = [
    {'name': 't0h0w0', 'avg': MIN_AVG_HOURS,  # Don't average, emergency state.
     'criteria': {'tmin': 0, 'tmax': 6, 'hmin': 0, 'hmax': 100.1, 'wmin': 0, 'wmax': 100},
     'action': {'heat': [60, 0]}},
    {'name': 't6h0w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 100},
     'action': {'mist': [60, 10020]}},  # Mist for 1 hour in a week.
    {'name': 't6h40w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 40, 'hmax': 80, 'wmin': 0, 'wmax': 100},
     'action': {'water': [5, 20155]}},  # Water for 5 min in 2 weeks.
    {'name': 't6h80w0', 'avg': 24,
     'criteria': {'tmin': 6, 'tmax': 17, 'hmin': 80, 'hmax': 100.1, 'wmin': 0, 'wmax': 100},
     'action': {'water': [5, 20155]}},  # Water for 5 min in 2 weeks.
    {'name': 't17h0w0', 'avg': 12,
     'criteria': {'tmin': 17, 'tmax': 25, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 100},
     'action': {'water': [5, 10075], 'mist': [60, 2820]}},  # Water for 5 min in 1 week. Mist for 1 hour every 2 days.
    {'name': 't17h40w0', 'avg': 12,
     'criteria': {'tmin': 17, 'tmax': 25, 'hmin': 40, 'hmax': 100.1, 'wmin': 0, 'wmax': 100},
     'action': {'water': [5, 10075]}},  # Water for 5 min in 1 week.
    {'name': 't25h0w0', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 0, 'hmax': 40, 'wmin': 0, 'wmax': 2},
     'action': {'water': [5, 10075], 'mix': {'mist': [30, 1410], 'fan': [60, 1380]}}},  # Water for 5 min in 1 week. Mist for 30 minutes every day at the most light. Interleave mist with fan for 1 hour.
    {'name': 't25h0w2', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 0, 'hmax': 40, 'wmin': 2, 'wmax': 100},
     'action': {'water': [5, 10075], 'mist': [30, 1410]}},  # Water for 30 min in 1 week. Mist for 30 minutes every day.
    {'name': 't25h40w0', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 40, 'hmax': 80, 'wmin': 0, 'wmax': 2},
     'action': {'water': [5, 10075], 'mix': {'mist': [5, 1435], 'fan': [60, 1380]}}},  # Water for 5 min in 1 week. Mist for 5 minutes every day at the most light. Interleave mist with fan for 1 hour.
    {'name': 't25h40w2', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 40, 'hmax': 80, 'wmin': 2, 'wmax': 100},
     'action': {'water': [5, 10075], 'mist': [5, 1435]}},  # Water for 5 min in 1 week. Mist for 5 minutes every day.
    {'name': 't25h80w0', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 80, 'hmax': 100.1, 'wmin': 0, 'wmax': 2},
     'action': {'water': [5, 10075], 'fan': [60, 1380]}},  # Water for 5 min in 1 week. fan for 1 hour at the most light and no wind.
    {'name': 't25h80w2', 'avg': 2,
     'criteria': {'tmin': 25, 'tmax': 28, 'hmin': 80, 'hmax': 100.1, 'wmin': 2, 'wmax': 100},
     'action': {'water': [5, 10075]}},  # Water for 5 min in 1 week.
    {'name': 't28h0w0', 'avg': 1,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 0, 'hmax': 80, 'wmin': 0, 'wmax': 2},
     'action': {'water': [7, 10073], 'mix': {'mist': [30, 90], 'fan': [60, 60]}}},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light. Interleave mist with fan for 1 hour.
    {'name': 't28h0w2', 'avg': 1,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 0, 'hmax': 80, 'wmin': 2, 'wmax': 100},
     'action': {'water': [7, 10073], 'mist': [30, 90]}},  # Water for 30 min in 1 week. Mist for 30 minutes every 2 hours at the most light.
    {'name': 't28h80w0', 'avg': 1,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 80, 'hmax': 100.1, 'wmin': 0, 'wmax': 2},
     'action': {'water': [7, 10073], 'fan': [30, 90]}},  # Water for 30 min in 1 week. fan for 30 minutes at the most light and no wind.
    {'name': 't28h80w2', 'avg': 1,
     'criteria': {'tmin': 28, 'tmax': 36, 'hmin': 80, 'hmax': 100.1, 'wmin': 2, 'wmax': 100},
     'action': {'water': [7, 10073]}},  # Water for 30 min in 1 week.
    {'name': 't36h0w0', 'avg': MIN_AVG_HOURS,  # Don't average, emergency state.
     'criteria': {'tmin': 36, 'tmax': 100, 'hmin': 0, 'hmax': 100.1, 'wmin': 0, 'wmax': 100},
     'action': {'mix': {'mist': [30, 30], 'fan': [30, 30]}, 'ac': [60, 0], 'shade': [400, 0]}},  # When t_amb > 36 or t_obj > 25
]


def activate(reason='unknown', force=False, **kwargs):
    '''Control the actuators.

    @:param kwargs: actuator_name=required_state. Can be boolean or string (on, off, value).
    @:returns string: message what was activated and deactivated.
    '''

    msg = []
    a = models.Actions()
    a.date = datetime.now()
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
        elif k == 'drip' or k == 'water':  # Backward compatibility :(
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
        print reason, "Action", a
        sys.stdout.write('Set action %s: %s' % (reason, repr(a)))
        sys.stdout.flush()
        try:
            a.save()
        except Exception as e:
            sys.stderr.write('On start: %s (%s)' % (e.message, type(e)))
    else:
        msg.append('No changes. Skip action')

    msg.append('reason: ' + reason)
    return ', '.join(msg)


def get_last_action(with_reason=False):
    '''
    :return: Dictionary of statuses of all actuators. Does not contain non-actuator data (ID, date, reason)
    '''
    a = {}
    try:
        # Avoid exception in case of empty database.
        a = models.Actions.objects.all().last()
    except Exception as e:  # TODO: Narrowise the catch, it's too wide...
        sys.stderr.write('%s -- On start: %s (%s)' % (a, e.message, type(e)))
        return a

    if with_reason:
        return a.get_all_fields(exclude=('id', 'date'))
    return a.get_all_fields()


def get_current_state():
    if not current_state:
        read_current_state()

    # Refresh current state calculation if data is obsolete
    dt = (datetime.now() - current_state[2]).total_seconds() / 60
    if current_state and dt >= 10:
        read_current_state()

    # Return empty dict and -1 if failed to retrieve current_state
    if not current_state:
        return {}, NO_DATA

    return current_state


def read_current_state():
    '''Calculate averages for all possible states. Choose the most appropriate state.
    Return status as full record of state_list and its index.
    '''

    # Read first the status with minimal averaging to catch emergency state (lowest and highest temperatures).
    status = calc_avg(MIN_AVG_HOURS)
    flag = False

    for i in range(len(state_list)):
        duration = state_list[i]['avg']
        # Skip repeating status calculation
        if status['duration'] != duration:
            status = calc_avg(duration)
            status['duration'] = duration

        # Abort current_state update if no meaningful data in the DB.
        if len(status.keys()) <= 2:
            return

        cr = state_list[i]['criteria']
        if cr['tmin'] <= status['t_amb'] < cr['tmax'] and cr['hmin'] <= status['rh'] < cr['hmax'] and cr['wmin'] <= status['wind'] < cr['wmax']:
            global current_state
            current_state = (state_list[i], i, datetime.now())
            flag = True
            break

    # Recovery procedure: when temperature is close to changing threshold there is a case when recalculation with
    # new average time brings result from previous state. In such conditions the status becomes None.
    # TODO: Optimize this.
    if not flag:
        status = calc_avg(2)
        # Abort current_state update if no meaningful data in the DB.
        if len(status.keys()) <= 2:
            return

        for i in range(len(state_list)):
            cr = state_list[i]['criteria']
            if cr['tmin'] <= status['t_amb'] < cr['tmax'] and cr['hmin'] <= status['rh'] < cr['hmax'] and cr['wmin'] <= status['wind'] < cr['wmax']:
                global current_state
                current_state = (state_list[i], i, datetime.now())
                break

    # sys.stdout.write('Read status: %s' % repr(current_state))


def calc_avg(duration):

    # Acquire relevant range of the data from the DB.
    ml = models.Sensors.objects.filter(date__gte=datetime.now() - timedelta(hours=duration)).values('wind', 'hpa', 't_amb', 't_obj', 'rh', 'lux')
    ed = defaultdict(int)  # Allow automatic adding of key is the key is not present in the dict.
    ed['duration'] = duration

    if ml.count() == 0:
        # Return last record if system was off long time.
        try:
            ml = [models.Sensors.objects.last().get_all_fields()]
        except:
            ml = []
        # Return empty dictionary if no records found (new database).
        if not ml:
            return ed

    # Sum all values for each parameter.
    for d in ml:
        for k, v in d.iteritems():
            ed[k] += v

    # Calc the avg
    try:
        count = ml.count()
    except:
        count = ml.count
    for k, v in ed.iteritems():
        ed[k] = ed[k] / count

    return ed


def act_current_state():
    '''Run this function in a thread. Do not join! It's never ending.
    This function just calls really working function in a loop.
    '''

    while True:
        ts = time.time()
        _run_state_action()
        # Sleep rest of time till end of minute
        time.sleep(60 - (time.time() - ts))


def set_timer(minutes):
    global manual_action_timer
    if type(minutes) is not int:
        try:
            minutes = int(minutes)
        except ValueError:
            minutes = 1
    manual_action_timer = [minutes, datetime.now()]


def get_next_action():
    '''Get dictionary of actuators in next planned state (on/off).
    Return None if no reasonable data available.
    '''

    la = get_last_action()          # Read actuators current status.
    state = get_current_state()[0]  # Take dictionary only. Index doesn't matter.

    # Abort calculation if no meaningful data available.
    if not state:
        return

    actions = state['action']
    result = []
    # Check if time gone per every single required action in given state
    for action, params in actions.iteritems():
        # Mix means: each actuator is enable for given time and disabled for all other times in the same dictionary.
        # i.e. mix can be split as simple action with predefined *order* of activity.
        if action in PRIM_ACTIONS:
            # Display 0 minutes (should be activated now) if negative difference calculated.
            next_change_in_min = max(params[not la[action]] - get_last_change_minutes(action, la[action]), 0)  # Dirty trick: use true/false as index
            next_action = not la[action]
            result.append((action, next_change_in_min, next_action))
        elif action == 'mix':  # mix action.
            for mix_action in MIX_ORDER:
                times = params[mix_action]  # [on, off]
                next_change_in_min = max(times[not la[mix_action]] - get_last_change_minutes(mix_action, la[mix_action]), 0)
                next_action = not la[mix_action]
                result.append((mix_action, next_change_in_min, next_action))
        else:  # Skip non-implemented actuators
            pass

    return result


def _run_state_action():
    '''Set actuators in appropriate position, which defined by current state.
    Actuator is eligible to turn on if:
    - currently it is off AND
    - passed enough time being off.
    Actuator is eligible to turn off if:
    - currently it is on AND
    - passed enough time being on.
    I.e. check eligibility of actuator to change state.
    '''

    la = get_last_action()          # Read actuators current status.
    state = get_current_state()[0]  # Take dictionary only. Index doesn't matter.

    # Abort calculation if no meaningful data available.
    if not state:
        return

    act_name = state['name']        # Keep name for reporting.
    actions = state['action']

    # Check if time gone per every single required action in given state
    for action, params in actions.iteritems():
        # Mix means: each actuator is enable for given time and disabled for all other times in the same dictionary.
        # i.e. mix can be split as simple action with predefined *order* of activity.
        if action in PRIM_ACTIONS:
            la = _invert_actuator_value_if_was_enough(la, action, params[not la[action]])  # Dirty trick: use true/false as index
        elif action == 'mix':  # mix action.
            na = copy.copy(la)
            for mix_action in MIX_ORDER:
                times = params[mix_action]  # [on, off]

                # Exit the loop if actuator inverted from False to True.
                # On contrary, continue the loop if actuator is inverted from True to False.
                na = _invert_actuator_value_if_was_enough(na, mix_action, times[not la[mix_action]])  # Dirty trick: use true/false as index

                if la[mix_action] != na[mix_action]:
                    la = na  # Update the last action. Prepare it for further activation.
                    # Exit the loop if actuator inverted from False to True. Relate to initial INVERTED value since:
                    # 1. The value was inverted by _invert_actuator_value_if_was_enough()
                    # 2. The new actions (na) was assigned back to la.
                    if la[mix_action]:
                        break
        else:  # Skip non-implemented actuators
            pass

    activate(reason='Automate for state: %s' % act_name, **la)


def _invert_actuator_value_if_was_enough(act_dict, act_name, time_in_state_min):
    '''Invert actuator value in the dictionary if was in same state longer than time_in_state_min.
    Don't change other actuators' state.

    :param act_dict:           contains current state of all actuators
    :param act_name:           points to required actuator
    :param time_in_state_min:  criteria for change.
    :return:                   dictionary with updated state.
    '''

    ad = copy.deepcopy(act_dict)
    eligible_change = get_last_change_minutes(act_name, act_dict[act_name]) > time_in_state_min
    if eligible_change:
        ad[act_name] = not ad[act_name]

    return ad


def is_enabled(actuator, automate=False):
    '''
    If automate == True:
        Returns True if last action to 'actuator' was automatic.
        Returns False if  last action to 'actuator' was manual.
    If automate == False:
        Returns True if last action to 'actuator' was manual.
        Returns False if  last action to 'actuator' was automatic.
    :param automate: bool
    :param actuator: str
    :return:
    '''
    la = get_last_action(with_reason=True)
    if not la:
        return False
    if 'automate' in la.reason.lower():
        return automate and la[actuator]
    else:
        return not automate and la[actuator]


def get_last_change_minutes(actuator, is_on):
    '''Return 'minutes' how long time ago the requested actuator was set in required state.
    Different approach of search comes from nature of the DB: after single "on" it can be number of "off".
    Return -1 if no such field in the DB.
    Return 0 if looking for 'off' state and actuator is currently "on".
    '''

    # Find last record with True value AND generated automatically
    filt = {'%s' % actuator: True, 'reason__icontains': 'automate'}
    try:  # Return -1 if no such field in the DB.
        qs = models.Actions.objects.filter(**filt).last()
    except exceptions.FieldError:
        return -1

    if not qs:
        return MAX_TIMEOUT

    if is_on:
        return _diff_datetime_mins(datetime.utcnow(), qs.date.replace(tzinfo=None))
    else:
        # Find last record with False value AFTER True value AND generated automatically
        filt = {'%s__%s' % ('date', 'gt'): qs.date, '%s' % actuator: False, 'reason__icontains': 'automate'}
        qs1 = models.Actions.objects.filter(**filt).first()
        # If no records then actuator is on now.
        if not qs1:
            la = get_last_action()
            if la and la[actuator]:
                return 0
            else:
                return MAX_TIMEOUT

        return _diff_datetime_mins(datetime.utcnow(), qs1.date.replace(tzinfo=None))


def _diff_datetime_mins(t1, t2):
    '''Calculate difference in minutes between datetime objects t1 and t2.
    t1 is considered to be greater (now).
    Both objects must be in the same timezone (UTC).
    '''

    return (t1 - t2).total_seconds() / 60


def send_message(subj, msg):
    # Send emergency mail
    sendmail.sendmail(subj, msg)
    # Send emergency IM
    pushb.send_note(subj, msg)

