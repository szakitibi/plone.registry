from zope.interface import implements, alsoProvides
from zope.schema import getFieldsInOrder
from zope.schema.interfaces import RequiredMissing
from plone.registry.interfaces import IRecordsProxy

from UserDict import DictMixin
import re

_marker = object()

class RecordsProxy(object):
    """A proxy that maps an interface to a number of records
    """
    
    implements(IRecordsProxy)
    
    def __init__(self, registry, schema, omitted=(), prefix=None):
        if prefix is None:
            prefix = schema.__identifier__ + '.'
        elif not prefix.endswith("."):
             prefix += '.'
        
        # skip __setattr__
        self.__dict__['__schema__'] = schema
        self.__dict__['__registry__'] = registry
        self.__dict__['__omitted__'] = omitted
        self.__dict__['__prefix__'] = prefix
        
        alsoProvides(self, schema)
        
    def __getattr__(self, name):
        if name not in self.__schema__:
            raise AttributeError(name)
        value = self.__registry__.get(self.__prefix__ + name, _marker)
        if value is _marker:
            value = self.__schema__[name].missing_value
        return value
        
    def __setattr__(self, name, value):
        if name in self.__schema__:
            full_name = self.__prefix__ + name
            if full_name not in self.__registry__:
                raise AttributeError(name)
            self.__registry__[full_name] = value
        else:
            self.__dict__[name] = value
    
    def __repr__(self):
        return "<RecordsProxy for %s>" % self.__schema__.__identifier__


class RecordsProxyCollection(DictMixin):
    """A proxy that maps a collection of RecordsProxy objects
    """

    _validkey = re.compile(r"([a-zA-Z][a-zA-Z0-9_]*)$").match

    # ord('.') == ord('/') - 1

    def __init__(self, registry, schema, check=True, omitted=(), prefix=None):
        if prefix is None:
            prefix = schema.__identifier__

        if not prefix.endswith("/"):
             prefix += '/'

        self.registry = registry
        self.schema = schema
        self.check = check
        self.omitted = omitted
        self.prefix = prefix

    def __getitem__(self, key):
        if self.has_key(key):
            prefix = self.prefix + key
            proxy = self.registry.forInterface(self.schema, self.check, self.omitted, prefix)
            return proxy
        raise KeyError(key)

    def __iter__(self):
        min = self.prefix
        max = self.prefix[:-1] + '0'
        keys = self.registry.records.keys(min, max)
        len_prefix = len(self._prefix)
        last = None
        for name in keys:
            name = name[len_prefix:]
            key, extra = name.split('/', 1)
            if key != last:
                yield key
                last = key

    def _validate(self, key):
        if not isinstance(key, basestring) or not self._validkey(key):
            raise TypeError('expected a valid key (alphanumeric or underscore, starting with alpha)')
        return str(key)

    def has_key(self, key):
        key = self._validate(key)
        prefix = self.prefix + key
        names = self.registry.records.keys(prefix+'.', prefix+'/')
        return bool(names)

    def add(self, key):
        key = self._validate(key)
        prefix = self.prefix + key
        self.registry.registerInterface(self.schema, self.omitted, prefix)
        proxy = self.registry.forInterface(self.schema, False, self.omitted, prefix)
        return proxy

    def __setitem__(self, key, value):
        key = self._validate(key)
        data = {}
        for name, field in getFieldsInOrder(self.schema):
            if name in self.omitted or field.readonly:
                continue
            attr = getattr(value, name, _marker)
            if attr is not _marker:
                data[name] = attr
            elif field.required and self.check:
                raise RequiredMissing(name)

        proxy = self.add(key)
        for name, attr in data.items():
            setattr(proxy, name, attr)

    def setdefault(self, key, failobj=None):
        if not self.has_key(key):
            if failobj is None:
                self.add(key)
            else:
                self[key] = failobj
        return self[key]

    def __delitem__(self, key):
        if not self.has_key(key):
            raise KeyError(key) 
        prefix = self.prefix + key
        names = list(self.registry.records.keys(prefix+'.', prefix+'/'))
        for name in names:
            del self.registry.records[name]
            