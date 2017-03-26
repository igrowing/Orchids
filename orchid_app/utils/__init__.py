import re

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
 
