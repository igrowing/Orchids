import sys
from collections import defaultdict
from datetime import datetime, timedelta

from orchid_app import actuators, utils, models
from orchid_app.utils import sendmail as sendmail, pushb


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
    '''Calculate averages for all possible states. Choose the most appropriate state.'''

    # Define tuples: lower temperature, time back for averaging.
    # Example: (6, 24)  means for temperatures of average 6deg.C and up use averaging of 24 hours.
    # 0.2 hours = 12 minutes, i.e. only last record is taken. This is set for emergency states (coldest and hottest).
    avg_preset = (  # Topmost tuple has top priority
        (36, 0.2),
        (28, 6),
        (17, 12),
        (6, 24),
        (0, 0.2),
    )

    # Check last status separately: it indicates on one of emergency states.
    status = calc_avg(avg_preset[-1][1])
    if status['t_amb'] >= avg_preset[-1][0]:
        return status  # TODO: consider string status return

    for t in avg_preset[-1]:
        status = calc_avg(t[1])
        if status['t_amb'] >= t[0]:
            return status  # TODO: consider string status return

    # TODO: define return value if nothing fits the preset temperatures (should not be thus)


def calc_avg(duration):

    # Acquire relevant range of the data from the DB.
    ml = models.Sensors.objects.filter(date__gte=datetime.now() - timedelta(hours=duration)).values('wind', 'hpa', 't_amb', 't_obj', 'rh', 'lux')
    ed = defaultdict(int)  # Allow automatic adding of key is the key is not present in the dict.

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