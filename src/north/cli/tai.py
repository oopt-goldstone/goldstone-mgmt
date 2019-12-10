import sys
import os
import re

sys.path.append('.')

from base import Object, InvalidInput
import pyang
import json
import yang as ly
import sysrepo as sr
import base64
import struct

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completer, Completion, FuzzyCompleter

TIMEOUT_MS = 10000

_FREQ_RE = re.compile(r'.+[kmgt]?hz$')

class TAICompleter(Completer):
    def __init__(self, config, state=None):
        self.config = config
        self.state = state

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

    def get_completions(self, document, complete_event=None):
        t = document.text.split()
        if len(t) == 0 or (len(t) == 1 and document.text[-1] != ' '):
            # attribute name completion
            for c in self.attrnames():
                if c.startswith(document.text):
                    yield Completion(c, start_position=-len(document.text))
        elif len(t) > 2:
            # invalid input for both get() and set(). no completion possible
            return
        else:
            # value completion

            # when self.state != None, this completer is used for get() command
            # which doesn't take value. so we don't need to do any completion 
            if self.state != None:
                return

            # complete the first argument
            doc = Document(t[0])
            c = list(self.get_completions(doc))
            if len(c) == 0:
                return
            elif len(c) > 1:
                # search perfect match
                l = [v.text for v in c if v.text == t[0]]
                if len(l) == 0:
                    return
                attrname = l[0]
            else:
                attrname = c[0].text

            text = t[1] if len(t) > 1 else ''

            for c in self.valuenames(attrname):
                if c.startswith(text):
                    yield Completion(c, start_position=-len(text))

class TAIObject(Object):

    def __init__(self, session, parent, name, type_):
        self.type_ = type_
        self.name = name
        self._get_hook = {}
        self._set_hook = {}
        super(TAIObject, self).__init__(session, parent)

        d = self.session.get_context().get_searchdirs()
        repo = pyang.FileRepository(d[0])
        ctx = pyang.Context(repo)

        m = self.session.get_context().get_module('goldstone-tai')
        v = m.print_mem(ly.LYS_IN_YANG, 0)

        ctx.add_module(None, v)
        mod = ctx.get_module('goldstone-tai')
        self.config = mod.search_one('grouping', 'tai-{}-config'.format(type_))
        self.state = mod.search_one('grouping', 'tai-{}-state'.format(type_))

        @self.command(FuzzyCompleter(TAICompleter(self.config, self.state)))
        def get(args):
            if len(args) != 1:
                raise InvalidInput('usage: get <name>')
            self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
            try:
                item = self.session.get_item('{}/state/{}'.format(self.xpath(), args[0]))
                if args[0] in self._get_hook:
                    print(self._get_hook[args[0]](item))
                else:
                    print(item.val_to_string())
            except RuntimeError:
                err = self.session.get_error()
                if err.error_cnt() > 0:
                    idx = err.error_cnt() - 1
                    print('err: {}, xpath: {}'.format(err.message(idx), err.xpath(idx)))
            self.session.session_switch_ds(sr.SR_DS_RUNNING)

        @self.command(TAICompleter(self.config))
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <name> <value>')
            if args[0] in self._set_hook:
                v = self._set_hook[args[0]](args[1])
            else:
                v = args[1]
            self.session.set_item_str('{}/config/{}'.format(self.xpath(), args[0]), v)
            self.session.apply_changes()

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
            tree = self.session.get_subtree(self.xpath(), TIMEOUT_MS)
            d = json.loads(tree.print_mem(ly.LYD_JSON, 0))
            print(d)
            self.session.session_switch_ds(sr.SR_DS_RUNNING)

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
        return '{0:.2f}THz'.format(int(item.val_to_string()) / 1e12)

def human_ber(item):
    return '{0:.2e}'.format(struct.unpack('>f', base64.b64decode(item.val_to_string()))[0])

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

    def __init__(self, session, parent, name):
        super(Module, self).__init__(session, parent, name, 'module')

        tree = self.session.get_subtree("{}[name='{}']".format(self.XPATH, self.name))
        self._map = json.loads(tree.print_mem(ly.LYD_JSON, 0))['goldstone-tai:module'][0]

        @self.command(WordCompleter(self._components('network-interface')))
        def netif(args):
            if len(args) != 1:
                raise InvalidInput('usage: netif <name>')
            return NetIf(self.session, self, args[0])

        @self.command(WordCompleter(self._components('host-interface')))
        def hostif(args):
            if len(args) != 1:
                raise InvalidInput('usage: hostif <name>')
            return HostIf(self.session, self, args[0])

    def __str__(self):
        return 'module({})'.format(self.name)

    def _components(self, type_):
        d = self._map
        return [v['name'] for v in d[type_]]

class Transponder(Object):
    XPATH = '/goldstone-tai:modules'

    def __init__(self, session, parent):
        super(Transponder, self).__init__(session, parent)

        tree = self.session.get_subtree(self.XPATH, TIMEOUT_MS)
        self._module_map = json.loads(tree.print_mem(ly.LYD_JSON, 0))

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            print(tree.print_mem(ly.LYD_JSON, 0))

        @self.command(WordCompleter(self._modules()))
        def module(args):
            if len(args) != 1:
                raise InvalidInput('usage: module <name>')
            return Module(self.session, self, args[0])

    def __str__(self):
        return 'transponder'

    def _modules(self):
        d = self._module_map
        return [v['name'] for v in d['goldstone-tai:modules']['module']]
