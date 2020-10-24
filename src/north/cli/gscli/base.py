from prompt_toolkit.document import Document
from prompt_toolkit.completion import (
    Completion,
    WordCompleter,
    FuzzyWordCompleter,
    NestedCompleter,
    DummyCompleter,
    FuzzyCompleter,
)
from prompt_toolkit.completion import Completer as PromptCompleter
from enum import Enum
from .cli import show_wrap

import sys
import subprocess
import logging

from abc import ABC, abstractmethod

stdout = logging.getLogger("stdout")


class InvalidInput(Exception):
    def __init__(self, msg, candidates=[]):
        self.msg = msg
        self.candidates = candidates

    def __str__(self):
        return self.msg


class BreakLoop(Exception):
    pass


class Completer(PromptCompleter):
    def __init__(self, command):
        self.command = command

    def get_completions(self, document, complete_event=None, nest=0):
        t = document.text.split()
        is_space_trailing = len(document.text) and (document.text[-1] == " ")
        if len(t) == 0 or (len(t) == 1 and not is_space_trailing):
            candidates = []
            for c in self.command.list():
                if c.startswith(document.text):
                    yield Completion(c, start_position=-len(document.text))
        else:
            c = self.command.get(t[0])
            if c:
                doc = Document(document.text[len(t[0]) :].lstrip())
                for v in c.completer.get_completions(
                    doc, complete_event, nest=nest + 1
                ):
                    yield v


class Command(ABC):

    SUBCOMMAND_DICT = {}

    def __init__(self, context=None, parent=None, name=None):
        self._completer = Completer(self)
        self.context = context
        self.parent = parent
        self.name = name

    @property
    def completer(self):
        return self._completer

    @abstractmethod
    def get(self, arg):
        candidates = [v for v in self.list() if v.startswith(arg)]
        if len(candidates) == 0:
            return None
        elif len(candidates) == 1:
            cmd = candidates[0]
        else:
            for c in candidates:
                # find a perfect match
                if arg == c:
                    cmd = arg
                    break
            else:
                return None  # no match

        return self.SUBCOMMAND_DICT[cmd](self.context, self, cmd)

    @abstractmethod
    def list(self):
        return self.SUBCOMMAND_DICT.keys()

    @abstractmethod
    def __call__(self, line):
        pass


class Object(object):
    XPATH = ""

    def __init__(self, parent, fuzzy_completion=False):
        self.parent = parent
        self._commands = {}
        self.fuzzy_completion = fuzzy_completion
        self.cli_op = show_wrap()
        self.mod_dict = self.cli_op.module_dict()
        self.show_dict = {
            "interface": {"brief": None, "description": None},
            "vlan": {"details": None},
            "datastore": None,
            "tech-support": None,
            "logging": None,
            "version": None,
            "transponder": self.mod_dict,
            "running-config": {
                "transponder": None,
                "onlp": None,
                "vlan": None,
                "interface": None,
                "aaa": None,
            },
        }

        @self.command(NestedCompleter.from_nested_dict(self.show_dict))
        def show(line):
            self.do_show(line)

        @self.command()
        def quit(line):
            self.close()
            if self.parent:
                return self.parent
            raise BreakLoop()

        @self.command()
        def exit(line):
            self.close()
            return sys.exit(0)

        if self.parent:
            for k, v in self.parent._commands.items():
                if v["inherit"]:
                    self._commands[k] = v

    def add_command(self, handler, completer=None, name=None):
        strict = False
        if isinstance(handler, Command):
            completer = handler.completer
            name = name if name else handler.name
            strict = True
        self.command(completer, name, strict=strict)(handler)

    def del_command(self, name):
        del self._commands[name]

    def get_completer(self, name):
        return self._commands.get(name, {}).get("completer", DummyCompleter())

    def close(self):
        pass

    def command(
        self,
        completer=None,
        name=None,
        async_=False,
        inherit=False,
        argparser=None,
        strict=False,
    ):
        def f(func):
            self._commands[name if name else func.__name__] = {
                "func": func,
                "completer": completer,
                "async": async_,
                "inherit": inherit,
                "argparser": argparser,
                "strict": strict,
            }

        return f

    def help(self, text="", short=True):
        text = text.lstrip()
        try:
            v = text.split()
            if len(text) > 0 and text[-1] == " ":
                # needs to show all candidates for the next argument
                v.append(" ")
            line = self.complete_input(v)
        except InvalidInput as e:
            return ", ".join(e.candidates)
        return line[-1].strip()

    def commands(self):
        return list(self._commands.keys())

    def completion(self, document, complete_event=None):
        # complete_event is None when this method is called by complete_input()
        if complete_event == None and len(document.text) == 0:
            return
        t = document.text.split()
        if len(t) == 0 or (len(t) == 1 and document.text[-1] != " "):
            # command completion
            if self.fuzzy_completion and complete_event:
                c = FuzzyWordCompleter(self.commands())
                for v in c.get_completions(document, complete_event):
                    yield v
            else:
                for cmd in self.commands():
                    if cmd.startswith(document.text):
                        yield Completion(cmd, start_position=-len(document.text))
        else:
            # argument completion
            # complete command(t[0]) first
            try:
                cmd = self.complete_input([t[0]])[0]
            except InvalidInput:
                return
            v = self._commands.get(cmd)
            if not v:
                return
            c = v["completer"]
            if c:
                if self.fuzzy_completion and complete_event:
                    c = FuzzyCompleter(c)

                # do argument completion with text after the command (t[0])
                new_document = Document(document.text[len(t[0]) :].lstrip())
                for v in c.get_completions(new_document, complete_event):
                    yield v

    def complete_input(self, line):

        if len(line) == 0:
            raise InvalidInput(
                f"invalid command. available commands: {self.commands()}",
                self.commands(),
            )

        for i in range(len(line)):
            doc = Document(" ".join(line[: i + 1]))
            c = list(self.completion(doc))
            if len(c) == 0:
                if i == 0:
                    raise InvalidInput(
                        f"invalid command. available commands: {self.commands()}",
                        self.commands(),
                    )
                else:
                    # t[0] must be already completed
                    v = self._commands.get(line[0])
                    assert v
                    cmpl = v["completer"]
                    if cmpl:
                        doc = Document(" ".join(line[:i] + [" "]))
                        candidates = list(v.text for v in self.completion(doc))
                        # if we don't have any candidates with empty input, it means the value needs
                        # to be passed as an opaque value
                        if len(candidates) == 0:
                            continue

                        raise InvalidInput(
                            f"invalid argument. candidates: {candidates}",
                            candidates,
                        )
                    else:
                        # no command completer, the command doesn't take any argument
                        continue
            elif len(c) > 1:
                # search for a perfect match
                t = [v for v in c if v.text == line[i]]
                if len(t) == 0:
                    candidates = [v.text for v in c]
                    target = "command" if i == 0 else "argument"
                    raise InvalidInput(
                        f"ambiguous {target}. candidates: {candidates}",
                        candidates,
                    )
                c[0] = t[0]
            line[i] = c[0].text
        return line

    def _exec(self, cmd):
        line = cmd.split()
        if len(line) > 0 and len(line[0]) > 0 and line[0][0] == "!":
            line[0] = line[0][1:]
            subprocess.run(" ".join(line), shell=True)
            return None, None
        cmd = self.complete_input(line[:1])
        cmd = self._commands[cmd[0]]

        # when strict == true, complete all inputs
        if cmd["strict"]:
            args = self.complete_input(line)[1:]
        else:
            args = line[1:]

        if cmd["argparser"]:
            args = cmd["argparser"].parse_args(line[1:])
        return cmd, args

    async def exec_async(self, cmd, no_fail=True):
        try:
            cmd, args = self._exec(cmd)
            if cmd == None:
                return self

            if cmd["async"]:
                return await cmd["func"](args)
            else:
                return cmd["func"](args)
        except InvalidInput as e:
            if not no_fail:
                raise e
            stdout.info(str(e))
        return self

    def exec(self, cmd, no_fail=True):
        try:
            cmd, args = self._exec(cmd)
            if cmd == None:
                return self

            if cmd["async"]:
                raise InvalidInput("async command not suppoted")
            return cmd["func"](args)
        except InvalidInput as e:
            if not no_fail:
                raise e
            stdout.info(str(e))
        return self

    def do_show(self, line):
        if len(line) == 0:
            raise InvalidInput(self.usage())

        if line[0] == "datastore":
            self.cli_op.datastore(line)

        elif line[0] == "running-config":
            self.cli_op.display_run_conf(line)

        elif line[0] == "tech-support":
            self.cli_op.tech_support(line)

        elif line[0] == "logging":
            self.cli_op.display_log(line)

        elif line[0] == "version":
            self.cli_op.get_version(line)

        elif line[0] == "transponder" or line[0] == "interface" or line[0] == "vlan":
            self.cli_op.display(line)

        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return (
            "usage:\n"
            " show interface (brief|description) \n"
            " show vlan details \n"
            " show transponder (<transponder_name>|summary)\n"
            " show logging \n"
            " show version \n"
            " show datastore <XPATH> [running|startup|candidate|operational|] [json|]\n"
            " show running-config [transponder|onlp|vlan|interface|aaa|]\n"
            " show tech-support"
        )
