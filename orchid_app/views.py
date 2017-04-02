from django.views.generic import TemplateView, CreateView, FormView, ListView, UpdateView, DetailView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from forms import OrchidForm, ActionsForm
from django.contrib import messages
from django.urls import reverse
from datetime import datetime
from . import models

import django_tables2 as tables
import actuators
import utils
import sys


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
    a = _get_last_action()
    if request.method == "POST":
        if form.is_valid():
            a.mist = request.POST.get("mist", False)
            a.water = request.POST.get("water", False)
            a.fan = request.POST.get("fan", False)
            a.light = request.POST.get("light", False)
            a.heat = request.POST.get("heat", False)

            msg = _activate(reason='Manual', mist=a.mist, drip=a.water, fan=a.fan, light=a.light, heat=a.heat)
            if [i for i in ['wrong', 'skip'] if i not in msg.lower()]:
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions tried: " + msg)

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

    return render(request, 'orchid_app/sensor_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table, 'actuators': a})


def action_list(request):
    form = ActionsForm(request.POST or None)
    a = _get_last_action()
    if request.method == "POST":
        if form.is_valid():
            a.mist = request.POST.get("mist", False)
            a.water = request.POST.get("water", False)
            a.fan = request.POST.get("fan", False)
            a.light = request.POST.get("light", False)
            a.heat = request.POST.get("heat", False)

            msg = _activate(reason='Manual', mist=a.mist, drip=a.water, fan=a.fan, light=a.light, heat=a.heat)
            if [i for i in ['wrong', 'skip'] if i not in msg.lower()]:
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions tried: " + msg)

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
    return render(request, 'orchid_app/action_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table, 'actuators': a})

def _activate(reason='unknown', force=False, **kwargs):
    '''Internal function. Control the actuators.

    @:param kwargs: actuator_name=required_state. Can be boolean or string (on, off, value).
    @:returns string: message what was activated and deactivated.
    '''

    #TODO: move out of views!

    msg = []
    a = models.Actions()
    a.date = datetime.now()
    a.water = a.mist = a.fan = a.light = a.heat = False
    a.reason = reason

    la = _get_last_action()

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


def _get_last_action():
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

def _verb(b):
    '''Convert boolean into verbal off/on.'''
    return ['off', 'on'][b] if type(b) == bool else b
