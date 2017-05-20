import re
import time
import cPickle
import hashlib

from functools import wraps


class Dict(dict):
    """Represent dictionary items as object attributes."""

    def filter(self, *args):
        return Dict((k, v) for k, v in self.items() if k in args)

    def __getattr__(self, name):
        if name in self.keys():
            return self[name]
        for key in self.keys():
            if name == _namify(key):
                return self[key]
        return dict.__getattribute__(self, name)

    def __setattr__(self, name, value):
        self[name] = value

    def _getAttributeNames(self, *args, **kwargs):
        """Support auto completion of keys in iPython."""
        return map(_namify, self.keys()) 


def _namify(key):
    return re.sub(r'[^\w]+', '_', key.lower()).strip('_') 


def dictify(obj, _dict=Dict, _list=list):
    if hasattr(obj, '_dictify'):
        obj = obj._dictify()
    if isinstance(obj, dict):
        return _dict((k, dictify(v, _dict, _list)) for k, v in obj.items())
    elif hasattr(obj, '__iter__'):
        return _list(dictify(v, _dict, _list) for v in obj)
    return obj

 
def as_key(obj):
    try:
        hash(obj)
        return obj
    except:
        return hashlib.md5(cPickle.dumps(obj)).hexdigest()
 

def memoize(keep=True, cache=None):
    '''Decorator: provide timed keeping functions results in memory.
    @:param keep: Boolean or number. Boolean keep or discards the cached data.
                  Number defines time in seconds to keep the cache with further discard of cache.
    @:param cache: empty dict. Separated cache names can be used if needed to keep similar function from different places.
    '''

    if cache is None:
        cache = {}
    INF = -1

    def _memoize0(func):
        @wraps(func)
        def _memoize1(*args, **kwargs):
            refresh = dict.pop(kwargs, '_refresh', False)
            timeout = dict.pop(kwargs, '_memoize', keep)
            timeout = INF if timeout is True else int(timeout)
            # Get the key name
            key = as_key((func, args, tuple(kwargs.items())))
            if refresh:
                cache.pop(key, None)
            if timeout and key in cache:
                t0, v = cache.get(key)
                if t0 == INF or t0 >= time.time():
                    return v
            value = func(*args, **kwargs)
            if not timeout:
                cache.pop(key, None)
                return value
            t0 = INF if timeout == INF else time.time() + timeout
            cache[key] = (t0, value)
            return value
        return _memoize1
    return _memoize0

