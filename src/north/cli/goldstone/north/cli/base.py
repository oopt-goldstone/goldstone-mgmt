from __future__ import annotations

from prompt_toolkit.document import Document
from prompt_toolkit.completion import (
    Completion,
    FuzzyCompleter,
    FuzzyWordCompleter,
    Completer as PromptCompleter,
    merge_completers,
)

from itertools import chain, zip_longest
import sys
import subprocess
import logging
import typing

stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class CLIException(Exception):
    pass


class InvalidInput(CLIException):
    def __init__(self, msg, candidates=[]):
        self.msg = msg
        self.candidates = candidates

    def __str__(self):
        return self.msg


class NoMatch(InvalidInput):
    pass


class AmbiguosInput(InvalidInput):
    pass


class BreakLoop(CLIException):
    pass


class Completer(PromptCompleter):
    def __init__(self, command):
        self.command = command

    def get_completions(self, document, complete_event=None):
        t = document.text.split()
        is_space_trailing = bool(len(document.text)) and (document.text[-1] == " ")
        if len(t) == 0 or (len(t) == 1 and not is_space_trailing):
            for c in self.command.list():
                if c.startswith(document.text):
                    yield Completion(c, start_position=-len(document.text))
        else:
            try:
                c = self.command.get(t[0])
            except InvalidInput:
                return

            if c:
                doc = Document(document.text[len(t[0]) :].lstrip())
                for v in c.completer.get_completions(doc, complete_event):
                    yield v


class Command(object):

    COMMAND_DICT = {}

    def __init__(self, context, parent, name, **options):
        c = Completer(self)
        additional_completer = options.get("additional_completer")
        if additional_completer:
            c = merge_completers([c, additional_completer])
        self._completer = c
        self.context = context
        self.parent = parent
        self.name = name
        self.options = options
        self.subcommand_dict = {}  # per-instance sub-commands
        registered_subcommands = getattr(self, "REGISTERED_COMMANDS", {})
        for k, v in registered_subcommands.items():
            if v[1] == None or (callable(v[1]) and v[1](self)):
                self.subcommand_dict[k] = (v[0], v[2])

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
            if cmd.name:
                r.append(cmd.name)
            cmd = cmd.parent

        return " ".join(reversed(r))

    def add_command(self, name: str, cmd: typing.Type[Command], **options):
        self.subcommand_dict[name] = (cmd, options)

    @classmethod
    def register_command(
        cls, name: str, cmd: typing.Type[Command], when=None, **options
    ):
        cls.REGISTERED_COMMANDS[name] = (cmd, when, options)

    def list_subcommands(self, include_hidden=False):
        for k, v in chain(self.COMMAND_DICT.items(), self.subcommand_dict.items()):
            if type(v) == tuple:
                cls, options = v
            else:
                cls, options = v, {}

            if not include_hidden and options.get("hidden"):
                continue

            yield k, (cls, options)

    # derived class overrides this method in typical case
    def arguments(self) -> List[str]:
        return []

    def _list(self, include_hidden=False) -> List[str]:
        args = self.arguments()
        return chain(
            args if args else [],
            (k for k, (cls, options) in self.list_subcommands(include_hidden)),
        )

    def list(self) -> List[str]:
        return self._list()

    @property
    def completer(self):
        return self._completer

    def complete_subcommand(self, arg, fuzzy=False, find_perfect_match=True, l=None):
        if l == None:
            l = list(self._list(True))
        candidates = [v for v in l if v.startswith(arg)]

        def cmpl(c, arg):
            return [v.text for v in c.get_completions(Document(arg), None)]

        if len(candidates) == 0 and fuzzy:
            c = FuzzyWordCompleter(l)
            candidates = cmpl(c, arg)

        c = self.options.get("additional_completer")
        if len(candidates) == 0 and c:
            candidates = cmpl(c, arg)
            if len(candidates) == 0 and fuzzy:
                c = FuzzyCompleter(c)
                candidates = cmpl(c, arg)

        if len(candidates) == 0:
            raise NoMatch(
                f"invalid command '{arg}'. available commands: {list(self.list())}",
                self.list(),
            )
        elif len(candidates) == 1:
            elected = candidates[0]
        else:
            l = candidates if find_perfect_match else []
            for c in l:
                # find a perfect match
                if arg == c:
                    elected = arg
                    break
            else:
                target = "argument" if self.parent else "command"
                raise AmbiguosInput(
                    f"ambiguous {target} '{arg}'. candidates: {candidates}", candidates
                )
        return elected

    def _get(self, name, default=None):
        cmd = self.COMMAND_DICT.get(name)
        options = {}
        if type(cmd) == tuple:
            cmd, options = cmd

        if cmd == None:
            cmd = self.subcommand_dict.get(name, default)
            if type(cmd) == tuple:
                cmd, options = cmd

        return cmd, options

    def get(self, arg, fuzzy=False) -> Type[Command]:
        elected = self.complete_subcommand(arg, fuzzy)

        cmd, options = self._get(elected, Command)

        if isinstance(cmd, type) and issubclass(cmd, Command):
            cmd = cmd(self.context, self, elected, **options)

        return cmd

    def _parse(self, elems, is_space_trailing, info, fuzzy, nest=0):
        if not elems:
            if is_space_trailing:
                l = [v.text for v in self.completer.get_completions(Document(""), None)]
                info.append(l)
            return
        try:
            find_perfect_match = len(elems) > 1 or is_space_trailing
            self.complete_subcommand(elems[0], fuzzy, find_perfect_match)
        except InvalidInput as e:
            info.append(e)
        else:
            c = self.get(elems[0], fuzzy)
            info.append(c.name)
            c._parse(elems[1:], is_space_trailing, info, fuzzy, nest + 1)

    def parse(self, text, fuzzy=False):
        elems = text.split()
        is_space_trailing = len(text) == 0 or (text[-1] == " ")
        info = []
        self._parse(elems, is_space_trailing, info, fuzzy)
        return (list(zip_longest(elems, info)), is_space_trailing)

    # derived class overrides this method in typical case
    def exec(self, line):
        if self.parent:
            line.insert(0, self.name)
            return self.parent.exec(line)

    def __call__(self, line, fuzzy=False):
        if type(line) == str:
            line = [line]

        no_completion = self.options.get("no_completion_on_exec")
        # if the command doesn't have any sub-commands and additional completer,
        # usually the desired behavior is to pass all arguments as is without
        # doing command completion
        if (
            no_completion == None
            and len(list(self.list())) == 0
            and "additional_completer" not in self.options
        ):
            no_completion = True

        # per-command fuzzy setting overrides conetext fuzzy setting
        fuzzy_override = self.options.get("fuzzy")
        if fuzzy_override != None:
            fuzzy = fuzzy_override

        if len(line) == 0 or no_completion:
            return self.exec(line)

        name = self.complete_subcommand(line[0], fuzzy)
        cmd, options = self._get(name)
        if cmd == None:
            l = line.copy()
            l[0] = name
            return self.exec(l)

        if isinstance(cmd, type) and issubclass(cmd, Command):
            cmd = cmd(self.context, self, name, **options)
        return cmd(line[1:], fuzzy)


class Context(object):
    XPATH = ""

    def __init__(self, parent, fuzzy_completion=None):
        self.parent = parent

        self._command = Command(self, None, "")
        registered_subcommands = getattr(self, "REGISTERED_COMMANDS", {})
        for k, v in registered_subcommands.items():
            if v[1] == None or (callable(v[1]) and v[1](self)):
                self._command.add_command(k, v[0], **v[2])

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

    def add_command(self, name, cmd, **options):
        assert isinstance(cmd, Command) or (
            isinstance(cmd, type) and issubclass(cmd, Command)
        )
        if isinstance(cmd, Command):
            assert name == cmd.name
        self._command.add_command(name, cmd, **options)

    @classmethod
    def register_command(
        cls, name: str, cmd: typing.Type[Command], when=None, **options
    ):
        cls.REGISTERED_COMMANDS[name] = (cmd, when, options)

    def list_subcommands(self):
        return self._command.list_subcommands()

    def get_completer(self, name):
        return self._command.get(name).completer

    def close(self):
        pass

    def command(
        self,
        completer=None,
        name=None,
        **options,
    ):
        def f(func):
            n = name if name else func.__name__

            d = {"exec": lambda self, line: func(line)}

            if completer:
                options["additional_completer"] = completer
                options["no_completion_on_exec"] = True

            cls = type(n, (Command,), d)
            cmd = cls(self, self._command, name=n, **options)
            self._command.add_command(n, cmd)

        return f

    def help(self, text=""):
        info, is_space_trailing = self._command.parse(text, self.fuzzy_completion)
        orig, parsed = info[-1]
        if parsed == None:
            return ""
        elif isinstance(parsed, InvalidInput):
            if is_space_trailing:
                return ""
            else:
                return ", ".join(parsed.candidates)
        elif isinstance(parsed, str):
            assert not is_space_trailing
            return parsed
        else:
            return ", ".join(parsed)

    def root(self):
        node = self
        while node.parent:
            node = node.parent
        return node

    @property
    def completer(self):
        c = self._command.completer
        if self.fuzzy_completion:
            c = FuzzyCompleter(c)
        return c

    def exec_host(self, line):
        line[0] = line[0][1:]
        try:
            subprocess.run(" ".join(line), shell=True)
        except KeyboardInterrupt:
            stdout.info("")
        return self

    def exec(self, cmd, no_fail=True):
        try:
            line = cmd.split()
            if len(line) > 0 and len(line[0]) > 0 and line[0][0] == "!":
                return self.exec_host(line)
            return self._command(line, self.fuzzy_completion)
        except CLIException as e:
            if not no_fail:
                raise e
            stderr.info(str(e))
        return self
