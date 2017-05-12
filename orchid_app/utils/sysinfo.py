#!/usr/bin/env python
'''
Read Hardware and system info.
Return as string or as dictionary.

--------- System --------------
In [46]: (psutil.time.time() - psutil.boot_time())/3600/24
Out[46]: 2.354974061065802
In [27]: psutil.time.tzname
Out[27]: ('IST', 'IDT')
In [28]: psutil.time.asctime()
Out[28]: 'Wed May 10 07:19:36 2017'
--------- CPU ----------
In [34]: psutil.cpu_freq()
Out[34]: scpufreq(current=1200.0, min=600.0, max=1200.0)
In [38]: psutil.cpu_percent()
Out[38]: 3.1
In [36]: psutil.cpu_count()
Out[36]: 4
-------- Memory ----------
In [21]: psutil.virtual_memory()
Out[21]: svmem(total=970477568, available=191057920, percent=80.3, used=697778176, free=23490560, active=474234880, inactive=383217664, buffers=29786112, cached=219422720, shared=18726912)
In [43]: psutil.disk_usage('/')
Out[43]: sdiskusage(total=29449383936L, used=4750770176L, free=23179071488L, percent=17.0)
--------- Network ----------
In [47]: psutil.net_if_stats()
Out[47]:
{'eth0': snicstats(isup=True, duplex=2, speed=100, mtu=1500),
 'lo': snicstats(isup=True, duplex=0, speed=0, mtu=65536),
 'wlan0': snicstats(isup=True, duplex=0, speed=0, mtu=1500)}
In [48]: psutil.net_io_counters()
Out[48]: snetio(bytes_sent=1030150293, bytes_recv=690415752, packets_sent=8091935, packets_recv=8062549, errin=0, errout=0, dropin=118048, dropout=0)
In [49]: psutil.net_if_addrs()
Out[49]:
{'eth0': [snic(family=2, address='10.100.101.6', netmask='255.0.0.0', broadcast='10.255.255.255', ptp=None),
  snic(family=10, address='fe80::ba27:ebff:fe4b:8cc8%eth0', netmask='ffff:ffff:ffff:ffff::', broadcast=None, ptp=None),
  snic(family=17, address='b8:27:eb:4b:8c:c8', netmask=None, broadcast='ff:ff:ff:ff:ff:ff', ptp=None)],
 'lo': [snic(family=2, address='127.0.0.1', netmask='255.0.0.0', broadcast=None, ptp=None),
  snic(family=10, address='::1', netmask='ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff', broadcast=None, ptp=None),
  snic(family=17, address='00:00:00:00:00:00', netmask=None, broadcast=None, ptp=None)],
 'wlan0': [snic(family=10, address='fe80::4ef5:4e65:49dd:f5a0%wlan0', netmask='ffff:ffff:ffff:ffff::', broadcast=None, ptp=None),
  snic(family=17, address='b8:27:eb:1e:d9:9d', netmask=None, broadcast='ff:ff:ff:ff:ff:ff', ptp=None)]}

'''

import time
import psutil
import pprint


def read_cpu_temp():
    try:
        f = open('/sys/class/thermal/thermal_zone0/temp', 'r')
        lines = f.readlines()
        f.close()
        return float(lines[0]) / 1000
    except:
        return 0.0


def read_system():
    _, _, days, hours, minutes, seconds, _, _, _ = time.gmtime(psutil.time.time() - psutil.boot_time())
    return {
        'uptime': '%s days, %s hours, %s minutes, %s seconds' % (days - 1, hours, minutes, seconds),
        'timezone': ', '.join(psutil.time.tzname),
        'datetime': psutil.time.asctime(),
    }


def read_cpu():
    d = {}
    current, min, max = psutil.cpu_freq()
    d['frequency'] = {'current': current, 'min': min, 'max': max}
    d['load'] = {'current': psutil.cpu_percent(), 'min': 0, 'max': 100}
    d['temp'] = {'current': round(read_cpu_temp(), 1), 'min': -20, 'max': 105}
    d['cores'] = psutil.cpu_count()
    return d


def read_memory():
    d = {}
    m = psutil.virtual_memory()
    d['RAM_MB'] = {'total': m.total/1024/1024, 'percent': m.percent, 'used': m.used/1024/1024}
    m = psutil.disk_usage('/')
    d['flash_GB'] = {
        'total': round(float(m.total)/1024/1024/1024, 2),
        'percent': m.percent,
        'used': round(float(m.used)/1024/1024/1024, 2),
    }
    return d


def read_network():
    d = {}
    s = psutil.net_if_stats()
    for k, v in s.iteritems():
        if k != 'lo':
            d[k] = {'speed': v.speed, 'mtu': v.mtu}
    s = psutil.net_io_counters()
    d['counters'] = {
        'sent_MB': int(s.bytes_sent/1024/1024),
        'recv_MB': int(s.bytes_recv/1024/1024),
        'errors': s.errin + s.errout,
        'drops': s.dropin + s.dropout,
    }
    return d


def get_sysinfo_d():
    # TODO: reconsider structure. Maybe list of lists is better than dict of dicts.
    return {
        'system': read_system(),
        'cpu': read_cpu(),
        'memory': read_memory(),
        'network': read_network(),
    }


def get_sysinfo_s():
    pass


def get_sysinfo_html():
    # TODO: Rewrite. This is ugly brute-force implementation. Build dynamic page generator.
    # Reconsidering data structure can help.
    # TODO: Add chart generation and output.

    d = get_sysinfo_d()

    # Get the template from file in relative path. The module can be called from different locations. So the template must be always available.
    tmp_file = '/'.join(__file__.split('/')[:-1]) + '/sysinfo_template.html'
    try:
        f = open(tmp_file, 'r')
        template = f.read()
        f.close()
    except Exception as e:
        return 'Error occurred on opening template.'

    datetime = d['system']['datetime']
    timezone = d['system']['timezone']
    uptime = d['system']['uptime']
    cores = d['cpu']['cores']
    f_min = d['cpu']['frequency']['min']
    f_max = d['cpu']['frequency']['max']
    f_current = d['cpu']['frequency']['current']
    l_min = d['cpu']['load']['min']
    l_max = d['cpu']['load']['max']
    l_current = d['cpu']['load']['current']
    t_min = d['cpu']['temp']['min']
    t_max = d['cpu']['temp']['max']
    t_current = d['cpu']['temp']['current']
    m_total = d['memory']['RAM_MB']['total']
    m_used = d['memory']['RAM_MB']['used']
    m_percent = d['memory']['RAM_MB']['percent']
    f_total = d['memory']['flash_GB']['total']
    f_used = d['memory']['flash_GB']['used']
    f_percent = d['memory']['flash_GB']['percent']
    tx = d['network']['counters']['sent_MB']
    rx = d['network']['counters']['recv_MB']
    errors = d['network']['counters']['errors']
    drops = d['network']['counters']['drops']
    e_speed = d['network']['eth0']['speed']
    e_mtu = d['network']['eth0']['mtu']
    w_speed = d['network']['wlan0']['speed']
    w_mtu = d['network']['wlan0']['mtu']
    pct = '%'

    return template % locals()

keys = []
values = []
def print_dict(d):
    '''
    Just for fun in programming: recursive function to print full hierarchy of nested dictionary.
    This is a stub for automated dictionary to HTML or to tables conversion.
    :param d:
    :return:
    '''
    for k, v in d.iteritems():
        if type(v) == dict:
            print_kv()
            print k
            print_dict(v)
        else:
            global keys, values
            keys.append(k)
            values.append(v)
    print_kv()


def print_kv():
    global keys, values
    if keys:
        print keys
        print values
        keys = []
        values = []


# Use this trick to execute the file. Normally, it's a module to be imported.
if __name__ == "__main__":
    print "Running as standalone:\n    " + __file__
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(get_sysinfo_d())
    print get_sysinfo_s()

