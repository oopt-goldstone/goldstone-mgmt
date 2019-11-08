#!/usr/bin/env python

import yang as ly
import sysrepo as sr

import json
from optparse import OptionParser

from prompt_toolkit import PromptSession
from prompt_toolkit.document import Document
from prompt_toolkit.completion import FuzzyCompleter, Completer, Completion, WordCompleter
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import run_in_terminal

VALUE_T = None

class InvalidInput(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

class Object(object):
    XPATH = ''

    def __init__(self, session, parent):
        self.session = session
        self.parent = parent
        self._commands = {}

        @self.command()
        def quit(line):
            return self.parent if self.parent else self

    def command(self, completers=[]):
        def f(func):
            def _inner(line):
                v = func(line)
                return v if v else self
            self._commands[func.__name__] = {'func': _inner, 'completers': completers}
        return f

    def help(self, text='?', short=True):
        text = text.strip()
        if text == '?':
            return ', '.join(self.commands())
        else:
            return 'WIP'

    def commands(self):
        return list(self._commands.keys())

    def completion(self, document, complete_event=None):
        # complete_event is None when this method is called by complete_input()
        if complete_event == None and len(document.text) == 0:
            return
        t = document.text.split()
        if len(document.text) != 0 and document.text[-1] == ' ':
            # argument completion when ' ' is typed after a command
            if len(t) == 0:
                return
            # complete command(t[0]) first
            try:
                t[0] = self.complete_input([t[0]])[0]
            except InvalidInput:
                return
            v = self._commands.get(t[0])
            if not v:
                return
            c = v['completers']
            if len(c) == 0 or len(t) > len(c):
                return
            if c[len(t)-1]:
                new_document = Document('')
                for v in c[len(t)-1].get_completions(new_document, complete_event):
                    yield v
            else:
                # if VALUE_T, the argument is a value so no completion possible
                pass
        elif len(t) < 2:
            # command completion
            text = '' if len(t) == 0 else t[0]
            for cmd in self.commands():
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        elif len(t) > 1:
            # argument completion

            # complete command(t[0]) first
            try:
                t[0] = self.complete_input([t[0]])[0]
            except InvalidInput:
                return
            v = self._commands.get(t[0])
            if not v:
                return
            c = v['completers']
            if len(c) == 0 or (len(t)-1) > len(c):
                return
            if c[len(t)-2]:
                new_document = Document(t[-1])
                for v in c[len(t)-2].get_completions(new_document, complete_event):
                    yield v
            else:
                # if VALUE_T, the argument is a value so no completion possible
                pass

    def complete_input(self, line):
        for i in range(len(line)):
            doc = Document(' '.join(line[:i+1]))
            c = list(self.completion(doc))
            if len(c) == 0:
                if i == 0:
                    raise InvalidInput('invalid command. available commands: {}'.format(self.commands()))
                else:
                    # t[0] must be alrady completed
                    v = self._commands.get(line[0])
                    assert(v)
                    c = v['completers']
                    if len(c) > (i-1) and c[i-1] == VALUE_T:
                        # if VALUE_T, the argument is a value so no completion possible
                        continue
                    else:
                        doc = Document(' '.join(line[:i] + [' ']))
                        raise InvalidInput('invalid argument. candidates: {}'.format(list(v.text for v in self.completion(doc))))
            elif len(c) > 1:
                # search perfect match
                t = [v for v in c if v.text == line[i]]
                if len(t) == 0:
                    raise InvalidInput('ambiguous {}. candidates: {}'.format('command' if i == 0 else 'argument', [v.text for v in c]))
                c[0] = t[0]
            line[i] = c[0].text
        return line 

    def exec(self, cmd):
        line = [v.strip() for v in cmd.split()]
        try:
            line = self.complete_input(line)
            if line[0] in self._commands:
                return self._commands[line[0]]['func'](line=line[1:])
            else:
                raise InvalidInput('invalid command. available commands: {}'.format(self.commands()))
        except InvalidInput as e:
            print(str(e))
        return self


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
            print('''Description:\t{}
    RPM:\t{} ({}%)
    Status:\t{}
    Capability:\t{}'''.format(d['state']['description'],
        fan['state']['rpm'],
        fan['state']['percentage'],
        '|'.join(fan['state']['status']),
        '|'.join(fan['state']['capability'])))
            return self

        attrs = WordCompleter(['percentage'])
        @self.command(completers=[attrs, VALUE_T])
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

        @self.command(completers=[WordCompleter(self._components('fan'))])
        def fan(args):
            if len(args) != 1:
                raise InvalidInput('usage: fan <name>')
            return Fan(self.session, self, 'fan', args[0])

        @self.command(completers=[WordCompleter(self._components('thermal'))])
        def thermal(args):
            if len(args) != 1:
                raise InvalidInput('usage: thermal <name>')
            return Component(self.session, self, 'thermal', args[0])

        @self.command(completers=[WordCompleter(self._components('psu'))])
        def psu(args):
            if len(args) != 1:
                raise InvalidInput('usage: psu <name>')
            return Component(self.session, self, 'psu', args[0])

        @self.command(completers=[WordCompleter(self._components('led'))])
        def led(args):
            if len(args) != 1:
                raise InvalidInput('usage: led <name>')
            return Component(self.session, self, 'led', args[0])

    def __str__(self):
        return 'platform'

    def _components(self, type_):
        d = self._component_map
        return [v['name'] for v in d['goldstone-onlp:components']['component'] if v['state']['type'] == type_.upper()]

class Root(Object):
    XPATH = '/'

    def __init__(self, sess):
        super(Root, self).__init__(sess, None)

        @self.command()
        def platform(line):
            if len(line) != 0:
                raise InvalidInput('usage: platform[cr]')
            return Platform(self.session, self)

    def __str__(self):
        return ''


class GoldstoneShellCompleter(Completer):
    def __init__(self, context):
        self.context = context 

    def get_completions(self, document, complete_event):
        return self.context.completion(document, complete_event)


class GoldstoneShell(object):
    def __init__(self, sess=None):
        if sess == None:
            conn = sr.Connection()
            sess = sr.Session(conn)
        self.context = Root(sess)

        #TODO dynamic command generation

        self.completer = GoldstoneShellCompleter(self.context)

        self.default_input = ''

        #TODO subscribe to global error message bus

    def prompt(self):
        c = self.context
        l = [str(c)]
        while c.parent:
            l.insert(0, str(c.parent))
            c = c.parent
        if len(l) == 1:
            return '> '
        return '/'.join(l)[1:] + '> '

    def exec(self, cmd: list):
        self.context = self.context.exec(cmd)
        self.completer.context = self.context
        self.default_input = ''

    def bindings(self):
        b = KeyBindings()

        @b.add('?')
        def _(event):
            buf = event.current_buffer
            original_text = buf.text
            buf.insert_text('?')
            buf.insert_line_below()
            buf.insert_text(event.app.shell.context.help())
            event.app.exit('')
            event.app.shell.default_input = original_text

#        @b.add(' ')
#        def _(event):
#            buf = event.current_buffer
#            if len(buf.text.strip()) > 0 and len(buf.text) == buf.cursor_position:
#                candidates = list(event.app.shell.context.completion(buf.document))
#                if len(candidates) == 1:
#                    c = candidates[0]
#                    buf.insert_text(c.text[-c.start_position:])
#                buf.cancel_completion()
#            buf.insert_text(' ')

        return b

def loop():
    session = PromptSession()

    default_prompt = '> '
    prompt = default_prompt

    shell = GoldstoneShell()

    while True:
        c = shell.completer
        p = shell.prompt()
        b = shell.bindings()
        session.app.shell = shell
        line = session.prompt(p, completer=c, key_bindings=b, default=shell.default_input)
        if len(line) > 0:
            shell.exec(line)


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-v', '--verbose', action='store_true')
    (options, args) = parser.parse_args()

    if options.verbose:
        log = sr.Logs()
        log.set_stderr(sr.SR_LL_DBG)

    loop()
