from __future__ import annotations

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
from prompt_toolkit.completion import merge_completers
from enum import Enum
from itertools import chain

import sys
import subprocess
import logging
import typing

stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class CLIException(Exception):
    pass


class LockedError(CLIException):
    def __init__(self, msg, e):
        self.msg = msg
        self.e = e

    def __str__(self):
        return self.msg


class InvalidInput(CLIException):
    def __init__(self, msg, candidates=[]):
        self.msg = msg
        self.candidates = candidates

    def __str__(self):
        return self.msg


class BreakLoop(CLIException):
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


class Command(object):

    SUBCOMMAND_DICT = {}

    def __init__(self, context=None, parent=None, name=None, additional_completer=None):
        c = Completer(self)
        if additional_completer:
            c = merge_completers([c, additional_completer])
        self._completer = c
        self.context = context
        self.parent = parent
        self.name = name
        self.options = set()
        self.subcommand_dict = {}  # per-instance sub-commands
        registered_subcommands = getattr(self, "REGISTERED_SUBCOMMANDS", {})
        for k, v in registered_subcommands.items():
            if v[1] == None or (callable(v[1]) and v[1](self)):
                self.subcommand_dict[k] = v[0]

    def add_sub_command(self, name: str, cmd: typing.Type[Command]):
        self.subcommand_dict[name] = cmd

    def list_subcommands(self):
        return chain(self.SUBCOMMAND_DICT.items(), self.subcommand_dict.items())

    @classmethod
    def register_sub_command(cls, name: str, cmd: typing.Type[Command], when=None):
        cls.REGISTERED_SUBCOMMANDS[name] = (cmd, when)

    @property
    def completer(self):
        return self._completer

    def complete_subcommand(self, arg):
        candidates = [v for v in self.list() if v.startswith(arg)]
        if len(candidates) == 0:
            return None
        elif len(candidates) == 1:
            elected = candidates[0]
        else:
            for c in candidates:
                # find a perfect match
                if arg == c:
                    elected = arg
                    break
            else:
                return None  # no match
        return elected

    def get(self, arg) -> Type[Command]:
        elected = self.complete_subcommand(arg)
        if elected == None:
            return None
        cls = self.SUBCOMMAND_DICT.get(elected)

        if cls == None:
            cls = self.subcommand_dict.get(elected, Command)

        cmd = cls(self.context, self, elected)

        if isinstance(cmd, Option):
            self.options.add(elected)

        if isinstance(cmd, NoArgOption):
            return self
        else:
            return cmd

    def list(self) -> List[str]:
        return [
            v
            for v in chain(self.SUBCOMMAND_DICT.keys(), self.subcommand_dict.keys())
            if v not in self.options
        ]

    def exec(self, line):
        if self.parent:
            line.insert(0, self.name)
            return self.parent.exec(line)

    def hidden(self):
        return False

    @property
    def root(self):
        cmd = self
        while cmd.parent:
            cmd = cmd.parent
        return cmd

    def name_all(self):
        r = []
        cmd = self
        while cmd != None:
            r.append(cmd.name)
            cmd = cmd.parent

        return " ".join(reversed(r))

    def __call__(self, line):
        if type(line) == str:
            line = [line]
        if len(line) == 0:
            return self.exec(line)

        elected = self.complete_subcommand(line[0])
        cmd = self.SUBCOMMAND_DICT.get(elected)
        if cmd == None:
            cmd = self.subcommand_dict.get(elected)

        if cmd:
            return cmd(self.context, self, line[0])(line[1:])
        else:
            return self.exec(line)


class Choice(Command):
    def __init__(
        self, choices, context=None, parent=None, name=None, additional_completer=None
    ):
        super().__init__(context, parent, name, additional_completer)
        self.choices = choices

    def list(self):
        if callable(self.choices):
            return self.choices()
        else:
            return self.choices


class Option(Command):
    pass


class NoArgOption(Option):
    def __call__(self, line):
        self.parent.options.add(self)
        self.parent(line)


class Object(object):
    XPATH = ""

    def __init__(self, parent, fuzzy_completion=None):
        self.parent = parent
        self._commands = {}

        if fuzzy_completion == None:
            if parent == None:
                fuzzy_completion = False
            else:
                fuzzy_completion = parent.fuzzy_completion

        self.fuzzy_completion = fuzzy_completion

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

    def add_command(self, handler, completer=None, name=None, strict=None, hidden=None):
        if isinstance(handler, Command):
            completer = lambda: handler.completer
            name = name if name else handler.name
            assert name != None
            if handler.name == None:
                handler.name = name
            strict = True if strict == None else strict
            if hidden == None:
                hidden = handler.hidden
        else:
            strict = False if strict == None else strict
            hidden = False if hidden == None else hidden
        self.command(completer, name, strict=strict, hidden=hidden)(handler)

    def del_command(self, name):
        del self._commands[name]

    def get_completer(self, name):
        v = self._commands.get(name, {}).get("completer", DummyCompleter())
        if callable(v):
            return v()

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
        hidden=False,
    ):
        def f(func):
            self._commands[name if name else func.__name__] = {
                "func": func,
                "completer": completer,
                "async": async_,
                "inherit": inherit,
                "argparser": argparser,
                "strict": strict,
                "hidden": hidden,
            }

        return f

    def help(self, text="", short=True):
        orig = self.fuzzy_completion
        self.fuzzy_completion = False
        text = text.lstrip()
        try:
            v = text.split()
            if len(text) > 0 and text[-1] == " ":
                # needs to show all candidates for the next argument
                v.append(" ")
            line = self.complete_input(v)
        except InvalidInput as e:
            return ", ".join(e.candidates)
        finally:
            self.fuzzy_completion = orig
        return line[-1].strip()

    def root(self):
        node = self
        while node.parent:
            node = node.parent
        return node

    def commands(self, include_hidden=False):
        def hide(v):
            hidden = v.get("hidden", False)
            if type(hidden) == bool:
                return hidden
            elif callable(hidden):
                return hidden()

        return list(
            k for k, v in self._commands.items() if include_hidden or not hide(v)
        )

    def completion(self, document, complete_event=None):
        # complete_event is None when this method is called by complete_input()
        if complete_event == None and len(document.text) == 0:
            return

        include_hidden = complete_event == None

        t = document.text.split()
        if len(t) == 0 or (len(t) == 1 and document.text[-1] != " "):
            # command completion
            if self.fuzzy_completion and complete_event:
                c = FuzzyWordCompleter(self.commands(), WORD=True)
                for v in c.get_completions(document, complete_event):
                    yield v
            else:
                for cmd in self.commands(include_hidden):
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
            if callable(c):
                c = c()
            if c:
                if self.fuzzy_completion and complete_event:
                    c = FuzzyCompleter(c)

                # do argument completion with text after the command (t[0])
                new_document = Document(document.text[len(t[0]) :].lstrip())
                for v in c.get_completions(new_document, complete_event):
                    yield v

    def complete_input(self, line, complete_event=None):

        if len(line) == 0:
            raise InvalidInput(
                f"invalid command. available commands: {self.commands()}",
                self.commands(),
            )

        for i in range(len(line)):
            doc = Document(" ".join(line[: i + 1]))
            c = list(self.completion(doc, complete_event))
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
                    if callable(cmpl):
                        cmpl = cmpl()
                    if cmpl:
                        doc = Document(" ".join(line[:i] + [" "]))
                        candidates = list(
                            v.text for v in self.completion(doc, complete_event)
                        )
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
            try:
                subprocess.run(" ".join(line), shell=True)
            except KeyboardInterrupt:
                stdout.info("")
            return None, None
        cmd = self.complete_input(line[:1])
        cmd = self._commands[cmd[0]]

        if isinstance(cmd["func"], Command):
            return cmd, line[1:]

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
        except CLIException as e:
            if not no_fail:
                raise e
            stderr.info(str(e))
        return self

    def exec(self, cmd, no_fail=True):
        try:
            cmd, args = self._exec(cmd)
            if cmd == None:
                return self

            if cmd["async"]:
                raise InvalidInput("async command not suppoted")
            return cmd["func"](args)
        except CLIException as e:
            if not no_fail:
                raise e
            stderr.info(str(e))
        return self

    def __getattr__(self, name):
        if name in self._commands:
            return self._commands[name]["func"]
        raise AttributeError(f"no attribute '{name}'")
