import re
import os
import django_tables2 as tables
from datetime import datetime
from django.core import exceptions
from django.contrib import messages
from django.shortcuts import render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from . import models
from forms import ActionsForm, SystemForm
import orchid_app.controller as controller
import orchid_app.utils.sysinfo as sysinfo

import warnings
warnings.filterwarnings('ignore')


class SensorTable(tables.Table):
    date = tables.DateTimeColumn(short=True)  # still doesn't work.
    class Meta:
        model = models.Sensors
        fields = ('date', 't_amb', 't_obj', 'rh', 'lux', 'hpa', 'wind', 'water')


class ActionTable(tables.Table):
    date = tables.DateTimeColumn(short=True)  # still doesn't work.
    class Meta:
        model = models.Actions
        fields = ('date', 'water', 'mist', 'fan', 'light', 'heat', 'reason')


# @register.filter(name='myDate')
# def myDate(value, arg):
#     #arg is optional and not needed but you could supply your own formatting if you want.
#     dateformatted = value.strftime("%b %d, %Y at %I:%M %p")
#     return dateformatted


# @login_required
def list(request):
    # Use auto_id for further form changes
    form = ActionsForm(request.POST or None, auto_id=True)
    # Get actions template
    a = controller.get_last_action()

    if request.method == "POST":
        if form.is_valid():
            a = parse_user_input(a, request)

    for k, v in a.iteritems():
        a[k] = _verb(v)

    form.water = a.water

    qs = models.Sensors.objects.all().order_by('-date')  # filter(date=request.date
    paginator = Paginator(qs, 30)
    page = request.GET.get('page')
    try:
        table = paginator.page(page)
    except PageNotAnInteger:
        table = paginator.page(1)
    except EmptyPage:
        table = paginator.page(paginator.num_pages)

    # Keep reference to page. Dirty trick. TODO: improve.
    pp = table
    # Convert current page into table.
    table = SensorTable(table)
    total = qs.count()

    statuses = [False for i in range(len(controller.state_list))]
    i = controller.get_current_state()[1]
    if i != controller.NO_DATA:
        statuses[i] = True

    al = _get_next_actions_parsed()
    tl = _get_timer_actions_parsed()

    return render(request, 'orchid_app/sensor_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table,
                                                           'actuators': a, 'statuses': statuses, 'actionList': al,
                                                           'timerList': tl,
                                                           })


def parse_user_input(a, request):
    # Keep a copy for compare
    la = controller.get_last_action()
    a.mist = request.POST.get("mist", False)
    a.water = request.POST.get("water", False)
    a.fan = request.POST.get("fan", False)
    a.light = request.POST.get("light", False)
    a.heat = request.POST.get("heat", False)
    time = request.POST.get("time", 0)
    reason = 'Manual'
    suffix = ''  # Add it to indicate in the DB that timer is engaged. Dirty trick for stateless machine :(
    for k, v in a.iteritems():
        # Don't waste time on non-changes actions
        if v == la[k]:
            continue

        if v and int(time) > 0:
            # For ON action:
            # Set 'Manual' reason and Send long-time actions to background timer if time is given.
            # Else Do 0-time actions immediately.
            suffix = ' with timer for %s minutes' % time

        # # For OFF action.
        # # Set 'Automate' reason and Turn off actuator if was enabled automatically.
        # # Else Set 'Manual' reason and Turn off actuator.
        # if controller.is_enabled(automate=True, actuator=k):
        #     reason = 'Automate overridden by user'
        #     # Stop other actions compare. One overriding action is important and enough
        #     break

    msg = controller.activate(reason=reason + suffix, mist=a.mist, drip=a.water, fan=a.fan, light=a.light, heat=a.heat)
    if [i for i in ['wrong', 'skip'] if i not in msg.lower()]:
        messages.success(request, "Actions taken: " + msg)
    else:
        messages.error(request, "Actions tried: " + msg)

    return a


def _get_next_actions_parsed():
    '''Return list of actions and times in format per item:
    ['actuator', 'action', 'remaining_time']
    '''
    al = controller.get_next_action()
    if al:
        for i in range(len(al)):
            al[i] = (al[i][0].capitalize(), _verb(al[i][2]).capitalize(), 'Now' if al[i][1] < 1 else _humanize(al[i][1]))
    return al


def _get_timer_actions_parsed():
    '''Return list of actions and times in format per item:
    ['actuator', 'action', 'remaining_time']
    '''
    # Process timer
    res = []
    try:
        # Find last record with Timer enable
        filt = {'reason__icontains': 'with timer'}
        qs = models.Actions.objects.filter(**filt).last()

        if 'with timer' in qs.reason.lower():
            min_l = re.findall('(\d+) min', qs.reason.lower())
            secs = int(min_l[0]) * 60 if min_l else 0
            was_on = [k for k, v in qs.get_all_fields().iteritems() if v]
            if was_on:
                # Avoid exception in case of empty database.
                la = models.Actions.objects.last().get_all_fields()
                # print 'was_on', str(was_on), 'secs', str(secs), 'la', repr(la)
                for i in was_on:
                    if la[i]:  # was on and still on
                        dt = max(0, secs - (datetime.utcnow() - qs.date.replace(tzinfo=None)).total_seconds())
                        res.append((i.capitalize(), _verb(not la[i]).capitalize(), 'Now' if dt < 1 else _humanize(dt, with_secs=True)))

    except (exceptions.FieldError, ValueError, KeyError) as e:
        print 'Error DB query, looking for timer', repr(e)  # Till any action available

    return res


def action_list(request):
    form = ActionsForm(request.POST or None)
    a = controller.get_last_action()
    if request.method == "POST":
        if form.is_valid():
            a = parse_user_input(a, request)

    # Standartize/verbose actuator form values.
    for k, v in a.iteritems():
        a[k] = _verb(v)

    form.water = a.water
    qs = models.Actions.objects.all().order_by('-date')  # filter(date=request.date
    paginator = Paginator(qs, 30)
    page = request.GET.get('page')
    try:
        table = paginator.page(page)
    except PageNotAnInteger:
        table = paginator.page(1)
    except EmptyPage:
        table = paginator.page(paginator.num_pages)

    # Keep reference to page. Dirty trick. TODO: improve.
    pp = table
    # Convert current page into table.
    table = ActionTable(table)

    total = qs.count()

    statuses = [False for i in range(len(controller.state_list))]
    i = controller.get_current_state()[1]
    if i != controller.NO_DATA:
        statuses[i] = True

    al = _get_next_actions_parsed()
    tl = _get_timer_actions_parsed()

    return render(request, 'orchid_app/action_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table,
                                                           'actuators': a, 'statuses': statuses, 'actionList': al,
                                                           'timerList': tl,
                                                           })


def sysinfo_list(request):
    form = SystemForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            if 'update' in request.POST:
                print 'User requested the firmware update.'
                msg = 'User requested the firmware update.'
                res = controller.update_firmware()
            elif 'restart' in request.POST:
                print 'user requested runner restart.'
                msg = 'user requested runner restart.'
                res = os.system('sudo service orchid_runner restart') == 0

            if res:
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions failed: " + msg)

    si = sysinfo.get_sysinfo_html()
    chart_data = sysinfo.get_sysinfo_d()
    charts = {
        'CPU': chart_data['cpu']['load']['current'],
        'RAM': chart_data['memory']['RAM_MB']['percent'],
        'Flash': chart_data['memory']['flash_GB']['percent'],
        'Temp': chart_data['cpu']['temp']['current'],
    }

    return render(request, 'orchid_app/sysinfo_list.html', {'form': form, 'sysinfo': si, 'charts': charts})


def _verb(b):
    '''Convert boolean into verbal off/on.'''
    return ['off', 'on'][b] if type(b) == bool else b


def _humanize(fl, with_secs=False):
    '''Convert minutes or seconds into human readable string.'''

    fl = int(fl)
    if with_secs:
        s = fl % 60
        fl /= 60
    else:
        s = ''
    m = fl % 1440 % 60
    h = fl % 1440 / 60
    d = fl / 1440
    res = (str(d) + 'd') if d else ''
    res += (str(h) + 'h') if h else ''
    res += (str(m) + 'm') if m else ''
    res += (str(s) + 's') if s else ''
    return res if res else 0

