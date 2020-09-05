import sys
import os
import re

from .base import Object, InvalidInput, Completer
from pyang import repository, context

import sysrepo as sr
import base64
import struct

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, FuzzyCompleter

_FREQ_RE = re.compile(r'.+[kmgt]?hz$')

class TAICompleter(Completer):
    def __init__(self, config, state=None):
        self.config = config
        self.state = state

        # when self.state != None, this completer is used for get() command
        # which doesn't take value. so we don't need to do any completion 
        hook = lambda : self.state != None
        super(TAICompleter, self).__init__(self.attrnames, self.valuenames, hook)

    def attrnames(self):
        l = [v.arg for v in self.config.substmts]
        if self.state:
            l += [v.arg for v in self.state.substmts]
        return l

    def valuenames(self, attrname):
        for v in self.config.substmts:
            if attrname == v.arg:
                t = v.search_one('type')
                if t.arg == 'boolean':
                    return ['true', 'false']
                elif t.arg == 'enumeration':
                    return [e.arg for e in t.substmts]
                else:
                    return []
        return []

class TAIObject(Object):

    def __init__(self, conn, parent, name, type_):
        self.type_ = type_
        self.name = name
        self._get_hook = {}
        self._set_hook = {}
        self.session = conn.start_session()
        super(TAIObject, self).__init__(parent)

        d = self.session.get_ly_ctx().get_searchdirs()
        repo = repository.FileRepository(d[0])
        ctx = context.Context(repo)

        m = self.session.get_ly_ctx().get_module('goldstone-tai')
        v = m.print_mem("yang")

        ctx.add_module(None, v)
        mod = ctx.get_module('goldstone-tai')
        self.config = mod.search_one('grouping', 'tai-{}-config'.format(type_))
        self.state = mod.search_one('grouping', 'tai-{}-state'.format(type_))

        @self.command(FuzzyCompleter(TAICompleter(self.config, self.state)))
        def get(args):
            if len(args) != 1:
                raise InvalidInput('usage: get <name>')
            self.session.switch_datastore('operational')
            try:
                items = self.session.get_items('{}/state/{}'.format(self.xpath(), args[0]))
                for item in items:
                    if args[0] in self._get_hook:
                        print(self._get_hook[args[0]](item.value))
                    else:
                        print(item.value)
            except sr.errors.SysrepoCallbackFailedError as e:
                print(e)

        @self.command(TAICompleter(self.config))
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <name> <value>')
            if args[0] in self._set_hook:
                v = self._set_hook[args[0]](args[1])
            else:
                v = args[1]
            self.session.switch_datastore('running')

            if type(self) != Module:
                try:
                    self.session.get_data(self.parent.xpath())
                except sr.SysrepoNotFoundError:
                    self.session.set_item(f'{self.parent.xpath()}/config/name', self.parent.name)

            try:
                self.session.get_data(self.xpath())
            except sr.SysrepoNotFoundError:
                self.session.set_item(f'{self.xpath()}/config/name', self.name)

            self.session.set_item(f'{self.xpath()}/config/{args[0]}', v)

            self.session.apply_changes()

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.switch_datastore('operational')
            print(self.session.get_data(self.xpath()))
            self.session.switch_datastore('running')

def human_freq(item):
    if type(item) == str:
        try:
            int(item)
            return item
        except ValueError:
            item = item.lower()
            if not _FREQ_RE.match(item):
                raise InvalidInput('invalid frequency input. (e.g 193.50THz)')
            item = item[:-2]
            v = 1
            if item[-1] == 't':
                v = 1e12
            elif item[-1] == 'g':
                v = 1e9
            elif item[-1] == 'm':
                v = 1e6
            elif item[-1] == 'k':
                v = 1e3
            return str(round(float(item[:-1]) * v))
    else:
        return '{0:.2f}THz'.format(int(item) / 1e12)

def human_ber(item):
    return '{0:.2e}'.format(struct.unpack('>f', base64.b64decode(item))[0])

class HostIf(TAIObject):

    def xpath(self):
        return "{}/host-interface[name='{}']".format(self.parent.xpath(), self.name)

    def __init__(self, session, parent, name):
        super(HostIf, self).__init__(session, parent, name, 'host-interface')

    def __str__(self):
        return 'hostif({})'.format(self.name)

class NetIf(TAIObject):

    def xpath(self):
        return "{}/network-interface[name='{}']".format(self.parent.xpath(), self.name)

    def __init__(self, session, parent, name):
        super(NetIf, self).__init__(session, parent, name, 'network-interface')
        self._get_hook = {
            'tx-laser-freq': human_freq,
            'ch1-freq': human_freq,
            'min-laser-freq': human_freq,
            'max-laser-freq': human_freq,
            'current-tx-laser-freq': human_freq,
            'current-pre-fec-ber': human_ber,
            'current-post-fec-ber': human_ber,
            'current-prbs-ber': human_ber,
        }
        self._set_hook = {
            'tx-laser-freq': human_freq,
        }

    def __str__(self):
        return 'netif({})'.format(self.name)

class Module(TAIObject):
    XPATH = '/goldstone-tai:modules/module'

    def xpath(self):
        return "{}[name='{}']".format(self.XPATH, self.name)

    def __init__(self, conn, parent, name):
        super(Module, self).__init__(conn, parent, name, 'module')

        @self.command(WordCompleter(lambda : self._components('network-interface')))
        def netif(args):
            if len(args) != 1:
                raise InvalidInput('usage: netif <name>')
            return NetIf(conn, self, args[0])

        @self.command(WordCompleter(lambda : self._components('host-interface')))
        def hostif(args):
            if len(args) != 1:
                raise InvalidInput('usage: hostif <name>')
            return HostIf(conn, self, args[0])

    def __str__(self):
        return 'module({})'.format(self.name)

    def _components(self, type_):
        self.session.switch_datastore('operational')
        d = self.session.get_data("{}[name='{}']".format(self.XPATH, self.name), no_subs=True)
        d = d.get('modules', {}).get('module', {}).get(self.name, {})
        return [v['name'] for v in d.get(type_, [])]

class Transponder(Object):
    XPATH = '/goldstone-tai:modules'

    def close(self):
        self.session.stop()

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        super(Transponder, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.switch_datastore('operational')
            print(self.session.get_data(self.XPATH))

        @self.command(WordCompleter(self._modules()))
        def module(args):
            if len(args) != 1:
                raise InvalidInput('usage: module <name>')
            return Module(conn, self, args[0])

    def __str__(self):
        return 'transponder'

    def _modules(self):
        self.session.switch_datastore('operational')
        d = self.session.get_data(self.XPATH, no_subs=True)
        return [v['name'] for v in d.get('modules', {}).get('module', {})]
