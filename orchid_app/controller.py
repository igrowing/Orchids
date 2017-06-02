import os
import re
import sys
import time
from django.core import exceptions
from collections import defaultdict
from datetime import datetime, timedelta

from orchid_app import actuators, models, utils
from orchid_app.utils import sendmail, pushb, memoize

MIN_AVG_HOURS = 0.4   # TODO: reconsider the value
MAX_TIMEOUT = 999999  # Very long time indicated no action was found
MANUAL_TIMEOUT = 3600
NO_DATA = -1          # Used in get_current_state()
VERSION = '0.1.4'

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
#   Example: 'mix': {'mist': [5, 40], 'fan': [10, 35]}
#            means: Turn mist on for 5 minutes, then turn mist off anf turn fan on for 10 min, then turn fan off for 30 min and repeat.
# In this example, sum of on+off time for each actuator = full cycle time. 5+40=45, 10+35=45.
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
    Actuator is changed only if it's current state is different from requested.
    DB is updated only on any actuator change.

    @:param kwargs: actuator_name=required_state. Can be boolean or string (on, off, value).
    @:returns string: message what was activated and deactivated.
    '''

    msg = []
    a = models.Actions()
    la = get_last_action()

    for k, v in kwargs.iteritems():
        if type(v) == unicode or type(v) == str:
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
        a.date = datetime.now()
        a.reason = reason
        sys.stdout.write('Set action %s: %s' % (reason, repr(a)))
        sys.stdout.flush()
        try:
            a.save()
        except Exception as e:
            sys.stderr.write('On DB write: %s (%s)' % (e.message, type(e)))
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
        a = models.Actions.objects.last()
    except (exceptions.FieldError, ValueError, KeyError) as e:
        sys.stderr.write('%s -- On Action DB read: %s (%s)' % (a, e.message, type(e)))
        return a

    if not a:
        # Simulate empty default last automated action
        a = models.Actions()
        a['date'] = datetime(1, 1, 1)

    if with_reason:
        return a.get_all_fields(exclude=('id', 'date'))
    return a.get_all_fields()


def get_last_automated_action(with_reason=False):
    # Try to read last automated action.
    la = {}
    try:
        # Avoid exception in case of empty database.
        # Find last record generated automatically
        filt = {'reason__icontains': 'automate'}
        la = models.Actions.objects.filter(**filt).last()
    except (exceptions.FieldError, ValueError, KeyError) as e:
        sys.stderr.write('Error DB query: %s (%s)' % (e.message, type(e)))
        return la

    # Try to read last timer action.
    lt = {}
    try:
        # Avoid exception in case of empty database.
        # Find last record generated automatically
        filt = {'reason__icontains': 'timer off'}
        lt = models.Actions.objects.filter(**filt).last()
    except (exceptions.FieldError, ValueError, KeyError) as e:
        sys.stderr.write('Error DB query: %s (%s)' % (e.message, type(e)))
        return lt

    if la and lt:
        if lt.id > la.id:
            la = lt
    elif not la and lt:
        la = lt

    if not la:
        # Simulate empty default last automated action
        la = models.Actions()
        la['date'] = datetime(1, 1, 1)

    if with_reason:
        return la.get_all_fields(exclude=('id'))
    return la.get_all_fields(exclude=('id', 'reason'))


# Don't use Memoize decorator here: it doesn't remove obsolete data, i.e. once read current state will never refresh even when timeout expired.
def get_current_state():
    global current_state
    temp_cs = current_state
    if not current_state:
        read_current_state()

    # Refresh current state calculation if data is obsolete
    dt = (datetime.now() - current_state[2]).total_seconds() / 60
    if current_state and dt >= 10:
        read_current_state()

    # Return empty dict and -1 if failed to retrieve current_state
    if not current_state:
        return {}, NO_DATA

    if temp_cs != current_state:
        print "State changed to:", current_state[0]['name'], 'on:', str(current_state[2])

    return current_state


@memoize(keep=600)
def read_current_state():
    '''Calculate averages for all possible states. Choose the most appropriate state.
    Update current_state status as full record of state_list and its index.
    Return True if algorithm worked as standard.
    Return False if recovery procedure used or no state received.
    '''

    # Read first the status with minimal averaging to catch emergency state (lowest and highest temperatures).
    status = calc_avg(MIN_AVG_HOURS)
    flag = False
    global current_state

    for state in reversed(state_list):
        duration = state['avg']
        # Skip repeating status calculation
        if status['duration'] != duration:
            status = calc_avg(duration)
            status['duration'] = duration

        # Abort current_state update if no meaningful data in the DB.
        if len(status.keys()) <= 2:
            return flag

        cr = state['criteria']
        if cr['tmin'] <= status['t_amb'] < cr['tmax'] and cr['hmin'] <= status['rh'] < cr['hmax'] and cr['wmin'] <= status['wind'] < cr['wmax']:
            current_state = (state, state_list.index(state), datetime.now())
            flag = True
            break

    # Recovery procedure: when temperature is close to changing threshold there is a case when recalculation with
    # new average time brings result from previous state. In such conditions the status becomes None.
    # TODO: Optimize this.
    if not flag:
        status = calc_avg(2)
        # Abort current_state update if no meaningful data in the DB.
        if len(status.keys()) <= 2:
            return flag

        for state in reversed(state_list):
            cr = state['criteria']
            if cr['tmin'] <= status['t_amb'] < cr['tmax'] and cr['hmin'] <= status['rh'] < cr['hmax'] and cr['wmin'] <= status['wind'] < cr['wmax']:
                current_state = (state, state_list.index(state), datetime.now())
                break

    # sys.stdout.write('Read status: %s' % repr(current_state))
    return flag


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
    count = 0
    for d in ml:
        count += 1
        for k, v in d.iteritems():
            ed[k] += v

    # Return empty dict if somehow (how?) no items were counted.
    if count == 0:
        ed = defaultdict(int)  # Allow automatic adding of key is the key is not present in the dict.
        ed['duration'] = duration
        return ed

    # Calc the avg
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


def get_next_action():
    '''Get list of actuators in next planned state (on/off) in format.
    ((actuator, time_to_action_in_minutes, action),
    ...,
    )
    Return None if no reasonable data available.
    '''

    la = get_last_automated_action()          # Read actuators current status.
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
            # Example: 'mix': {'mist': [30, 90], 'fan': [60, 60]}
            for mix_action in MIX_ORDER:
                times = params[mix_action]  # [on, off]
                next_change_in_min = max(times[not la[mix_action]] - get_last_change_minutes(mix_action, la[mix_action]), 0)
                next_action = not la[mix_action]
                result.append((mix_action, next_change_in_min, next_action))
                # Exit the mix actions loop if action was Turn on: when mist is on, no need to turn on the fan. When mist is off then fan will be activated
                if next_action:
                    break
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

    # Process timer first.
    tr = get_timer_order()
    if tr:
        ad, t_rem = tr  # Unpack timer results
        filt = {'reason__icontains': 'timer off'}
        qs = models.Actions.objects.filter(**filt).last()
        dt = (datetime.now() - qs.date.replace(tzinfo=None)).total_seconds() / 60
        if t_rem < 0.5:  # Approximate to zero time. If statement t_rem <= 0 then it looks like 1 minute delay.
            activate(reason='Manual timer off', **ad)

        # Do not follow automated rules if timer is active.
        if dt < dt + t_rem:
            return

    # Process time-less manual action
    try:
        ma = models.Actions.objects.last()
        if ma.reason.lower() == 'manual' and any(ma.get_all_fields().values()):
            if (datetime.utcnow() - ma.date.replace(tzinfo=None)).total_seconds() > MANUAL_TIMEOUT:
                alert_actuator_on()
            return
    except:
        # In case of no data in DB or network failure (unable to send alert), return to normal automatic work.
        print "ERROR occurred during access to Actions DB or during attempt to send 'Too long manual on' alert.", str(datetime.now())

    state = get_current_state()[0]  # Take dictionary only. Index doesn't matter.

    # Abort calculation if no meaningful data available.
    if not state:
        return

    act_name = state['name']        # Keep name for reporting.
    reason = 'Automate for state: %s' % act_name

    # TODO: Consider actuators off for automated actions time calculation.

    la = get_last_automated_action()
    al = get_next_action()
    if al:
        for act, rem_min, todo in al:
            if rem_min <= 0:
                la[act] = todo

        # Sanity check: if something is on automatically and should not be in this state then turn it off.
        la = _sanity_check(la, state['action'])

        # print 'Intended action for:', act_name, str(la), str(datetime.now())
        activate(reason=reason, **la)


def _sanity_check(proposal, possible):
    possible = utils.flatten_dict(possible)

    for k, v in models.Actions().get_all_fields().iteritems():
        proposal[k] = proposal[k] if k in possible.keys() else False

    return proposal


def get_timer_order():
    '''Return a tuple of: (dictionary_of_actuators_and_actions, remaining_time_in_minutes).
    Return None if no timers active.
    Example:
        ({'mist': False, 'water': False}, 2)
    '''

    # Process timer
    try:
       # Find last record with Timer enable
       filt = {'reason__icontains': 'with timer'}
       qs = models.Actions.objects.filter(**filt).last()

       if qs:
           # Validate whether the action was disabled automatically already. Skip changes if found.
           last_on_id = qs.id
           min_l = re.findall('(\d+) min', qs.reason.lower())
           secs = int(min_l[0]) * 60 if min_l else 0

           # Collect what was on in list
           was_on = [k for k, v in qs.get_all_fields().iteritems() if v]

           # Filter out from was_on all actions that were disabled later (manually or automatically)
           for action in was_on:
               filt = {action: False, 'id__gt': last_on_id}
               qs1 = models.Actions.objects.filter(**filt).first()
               if qs1:
                   was_on.remove(action)

           # Time gone. Check if needed action.
           t_diff = secs - ((datetime.utcnow() - qs.date.replace(tzinfo=None)).total_seconds())
           la = models.Actions.objects.last().get_all_fields()
           if t_diff <= 0 and was_on:
               for i in was_on:
                   if la[i]:
                       la[i] = False

           return la, t_diff / 60

    except (exceptions.FieldError, ValueError, KeyError) as e:
       pass  # Till any action available


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
    except (exceptions.FieldError, ValueError, KeyError) as e:
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


@memoize(keep=3600)
def alert_actuator_on():
    ''' Send alert/reminder once in hour. '''

    a = models.Actions.objects.last()
    on = ', '.join([k.capitalize() for k, v in a.get_all_fields().iteritems() if v])
    t = str(round((datetime.utcnow() - a.date.replace(tzinfo=None)).total_seconds() / 3600.0, 1))

    subj = 'OrchidCare: %s turned on manually too long' % on
    msg = "%s was turned on manually on %s and not turned off till now. (Already on for %s hours.) \n" \
          "The automatic function of OrchidCare is blocked. Human attention is required to turn actuators off. \n" \
          "In case you're unable to turn actuator off for some reason, proceed to System information page and click " \
          "[Restart Runner] button. This forces all actuators off and restores automatic function of OrchidCare." % (on, str(a.date), t)

    send_message(subj, msg)


def send_message(subj, msg):
    # Send emergency mail
    sendmail.sendmail(subj, msg)
    # Send emergency IM
    pushb.send_note(subj, msg)


def update_firmware():
    '''
    Download and unpack latest software from GitHub.
    Consider automatic runner restart on FW update Positive completion.
    :return: bool: completed well or not.
    '''

    os.system('nohup /bin/bash /home/pi/Orchids/fw_update.sh &')
    return True

