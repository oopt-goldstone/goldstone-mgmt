import sys
import os

sys.path.append('.')

from base import Object, InvalidInput
import json
import yang as ly
import sysrepo as sr

from prompt_toolkit.completion import WordCompleter

class Component(Object):
    XPATH = '/goldstone-onlp:components/component'

    def __init__(self, session, parent, type_, name):
        if type_ not in ['fan', 'thermal', 'psu', 'led']:
            raise InvalidInput('invalid component')
        self._type = type_
        self.name = name
        super(Component, self).__init__(session, parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
            tree = self.session.get_subtree("{}[name='{}']".format(self.XPATH, self.name))
            d = json.loads(tree.print_mem(ly.LYD_JSON, 0))
            print(d['goldstone-onlp:component'][0][self._type])
            self.session.session_switch_ds(sr.SR_DS_RUNNING)

    def __str__(self):
        return '{}({})'.format(self._type, self.name)


class Fan(Component):

    def __init__(self, *args):
        super(Fan, self).__init__(*args)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
            tree = self.session.get_subtree("{}[name='{}']".format(self.XPATH, self.name))
            d = json.loads(tree.print_mem(ly.LYD_JSON, 0))
            d = d['goldstone-onlp:component'][0]
            fan = d[self._type]
            print(d)

        attrs = WordCompleter(['percentage'])

        @self.command(attrs)
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <attribute> <value>[cr]')
            self.session.set_item_str("{}[name='{}']/fan/config/{}".format(self.XPATH, self.name, args[0]), args[1])
            self.session.apply_changes()
            # raise InvalidInput exception when value is invalid
            return self

class Platform(Object):
    XPATH = '/goldstone-onlp:components'

    def __init__(self, session, parent):
        super(Platform, self).__init__(session, parent)

        self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
        tree = self.session.get_subtree(self.XPATH)
        self.session.session_switch_ds(sr.SR_DS_RUNNING)
        self._component_map = json.loads(tree.print_mem(ly.LYD_JSON, 0))

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.session_switch_ds(sr.SR_DS_OPERATIONAL)
            tree = self.session.get_subtree(self.XPATH)
            print(tree.print_mem(ly.LYD_JSON, 0))
            self.session.session_switch_ds(sr.SR_DS_RUNNING)

        @self.command(WordCompleter(self._components('fan')))
        def fan(args):
            if len(args) != 1:
                raise InvalidInput('usage: fan <name>')
            return Fan(self.session, self, 'fan', args[0])

        @self.command(WordCompleter(self._components('thermal')))
        def thermal(args):
            if len(args) != 1:
                raise InvalidInput('usage: thermal <name>')
            return Component(self.session, self, 'thermal', args[0])

        @self.command(WordCompleter(self._components('psu')))
        def psu(args):
            if len(args) != 1:
                raise InvalidInput('usage: psu <name>')
            return Component(self.session, self, 'psu', args[0])

        @self.command(WordCompleter(self._components('led')))
        def led(args):
            if len(args) != 1:
                raise InvalidInput('usage: led <name>')
            return Component(self.session, self, 'led', args[0])

    def __str__(self):
        return 'platform'

    def _components(self, type_):
        d = self._component_map
        return [v['name'] for v in d.get('goldstone-onlp:components', {}).get('component', []) if v['state']['type'] == type_.upper()]
