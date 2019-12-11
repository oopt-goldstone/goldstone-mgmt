#!/usr/bin/env python

import sysrepo as sr
from optparse import OptionParser
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer

import sys
import os

sys.path.append('.')

from base import Object, InvalidInput
from onlp import Platform
from tai  import Transponder

class Root(Object):
    XPATH = '/'

    def __init__(self, sess):
        super(Root, self).__init__(sess, None)

        @self.command()
        def platform(line):
            if len(line) != 0:
                raise InvalidInput('usage: platform[cr]')
            return Platform(self.session, self)

        @self.command()
        def transponder(line):
            if len(line) != 0:
                raise InvalidInput('usage: transponder[cr]')
            return Transponder(self.session, self)

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
            help_msg = event.app.shell.context.help(buf.text)
            buf.insert_text('?')
            buf.insert_line_below(copy_margin=False)
            buf.insert_text(help_msg)
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
