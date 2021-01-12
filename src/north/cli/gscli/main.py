#!/usr/bin/env python

import sysrepo as sr

import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import (
    Completer,
    NestedCompleter,
    FuzzyWordCompleter,
)
from prompt_toolkit import patch_stdout

import sys
import os
import subprocess
import logging
import asyncio
import json
import time

from .base import InvalidInput, BreakLoop, Command, CLIException
from .cli import GSObject as Object
from .tai_cli import Transponder
from .sonic_cli import Interface_CLI, Vlan_CLI
from .sonic import Sonic
from .system_cli import AAA_CLI, TACACS_CLI, Mgmt_CLI, System
from .system import AAA, TACACS, Mgmtif

logger = logging.getLogger(__name__)

stdout = logging.getLogger("stdout")


class NotificationCommand(Command):
    SUBCOMMAND_DICT = {
        "enable": Command,
        "disable": Command,
    }

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(self.usage())

        if line[0] == "enable":
            self.context.enable_notification()
        else:
            self.context.disable_notification()

    def usage(self):
        return f"usage: {self.parent.name} {self.name} [enable|disable]"


class SetCommand(Command):
    SUBCOMMAND_DICT = {
        "notification": NotificationCommand,
    }


class Root(Object):
    XPATH = "/"

    def __init__(self, conn):
        self.conn = conn
        self.session = conn.start_session()
        self.notif_session = None

        super().__init__(None, fuzzy_completion=True)
        self.sonic = Sonic(conn)
        self.aaa_cli = AAA_CLI(conn)
        self.tacacs_cli = TACACS_CLI(conn)
        self.aaa_sys = AAA(conn)
        self.tacacs_sys = TACACS(conn)
        self.mgmt = Mgmtif(conn)
        self.tacacs_complete = {"host": None}
        self.aaa_completion = {
            "authentication": {
                "login": {"default": {"group": {"tacacs": None}, "local": None}}
            }
        }
        self.no_dict = {
            "vlan": FuzzyWordCompleter(lambda: self.get_vid(), WORD=True),
            "aaa": {"authentication": {"login": None}},
            "tacacs-server": {"host": None},
        }
        # TODO:add timer for inactive user

        self.add_command(SetCommand(self, name="set"))

        @self.command()
        def save(line):
            if len(line) != 1:
                raise InvalidInput("usage: save <module name>")
            self.session.switch_datastore("startup")

            try:
                self.session.copy_config("running", line[0])
            except sr.SysrepoError as e:
                print(e)

        @self.command()
        def ping(line):
            try:
                png = " ".join(["ping"] + line)
                subprocess.call(png, shell=True)
            except KeyboardInterrupt:
                print("")
            except:
                print("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def traceroute(line):
            try:
                trct = " ".join(["traceroute"] + line)
                subprocess.call(trct, shell=True)
            except:
                print("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def hostname(line):
            try:
                hst_name = " ".join(["hostname"] + line)
                subprocess.call(hst_name, shell=True)
            except:
                print("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def system(line):
            if len(line) != 0:
                raise InvalidInput("usage: system[cr]")
            return System(conn, self)

        @self.command(FuzzyWordCompleter(lambda: self.get_modules(), WORD=True))
        def transponder(line):
            if len(line) != 1:
                raise InvalidInput("usage: transponder <transponder name>")
            elif line[0] in self.get_modules():
                return Transponder(conn, self, line[0])
            else:
                print(f"There is no device of name {line[0]}")
                return

        @self.command(
            FuzzyWordCompleter(
                lambda: (self.get_ifnames() + self.get_mgmt_ifname()), WORD=True
            )
        )
        def interface(line):
            if len(line) != 1:
                raise InvalidInput("usage: interface <ifname>")
            if line[0] in self.get_mgmt_ifname():
                return Mgmt_CLI(conn, self, line[0])
            else:
                return Interface_CLI(conn, self, line[0])

        @self.command()
        def date(line):
            self.date(line)

        # SYSTEM CLIs  -- START
        @self.command(NestedCompleter.from_nested_dict(self.aaa_completion))
        def aaa(line):
            self.aaa_cli.aaa(line)

        @self.command(
            NestedCompleter.from_nested_dict(self.tacacs_complete), name="tacacs-server"
        )
        def tacacs_server(line):
            self.tacacs_cli.tacacs_server(line)

        @self.command()
        def reboot(line):
            print(self.session.rpc_send("/goldstone-system:reboot", {}))

        @self.command()
        def shutdown(line):
            print(self.session.rpc_send("/goldstone-system:shutdown", {}))

        # SYSTEM CLIs  -- END

        @self.command(FuzzyWordCompleter(lambda: self.get_vid(), WORD=True))
        def vlan(line):
            if len(line) != 1:
                raise InvalidInput("usage: vlan <vlan-id>")
            if line[0].isdigit():
                return Vlan_CLI(conn, self, line[0])
            else:
                print("The vlan-id entered must be numbers and not letters")

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(line):
            if len(line) == 2:
                if line[0] == "vlan":
                    vlan_list = self.get_vid()
                    if line[1].isdigit():
                        if line[1] in vlan_list:
                            self.sonic.vlan.delete_vlan(line[1])
                        else:
                            print("The vlan-id provided doesn't exist")
                    else:
                        print("The vlan-id entered must be numbers and not letters")
                else:
                    raise InvalidInput(self.no_usage())
            elif len(line) == 3:
                if line[0] == "aaa":
                    if line[1] == "authentication" and line[2] == "login":
                        self.aaa_sys.set_no_aaa()
                    else:
                        print("Enter the valid no command for aaa")
                elif line[0] == "tacacs-server":
                    if line[1] == "host":
                        self.tacacs_sys.set_no_tacacs(line[2])
                    else:
                        print("Enter valid no command for tacacs-server")
                else:
                    raise InvalidInput(self.no_usage())
            else:
                raise InvalidInput(self.no_usage())

    def get_ifnames(self):
        return [v["name"] for v in self.sonic.port.get_interface_list("operational")]

    def get_mgmt_ifname(self):
        return [v["name"] for v in self.mgmt.get_mgmt_interface_list("operational")]

    def get_vid(self):
        path = "/goldstone-vlan:vlan/VLAN/VLAN_LIST"
        self.session.switch_datastore("operational")
        try:
            data_tree = self.session.get_data_ly(path)
            vlan_map = json.loads(data_tree.print_mem("json"))["goldstone-vlan:vlan"][
                "VLAN"
            ]["VLAN_LIST"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return []

        self.session.switch_datastore("running")
        return [str(v["vlanid"]) for v in vlan_map]

    def get_modules(self):
        path = "/goldstone-tai:modules"
        self.session.switch_datastore("operational")
        d = self.session.get_data(path, no_subs=True)
        return [v["name"] for v in d.get("modules", {}).get("module", {})]

    def date(self, line):
        date = " ".join(["date"] + line)
        subprocess.call(date, shell=True)

    def no_usage(self):
        return (
            "usage:\n"
            "no vlan <vid>\n"
            "no aaa authentication login\n"
            "no tacacs-server host <address>"
        )

    def enable_notification(self):
        if self.notif_session:
            logger.warning("notification already enabled")
            return
        self.notif_session = self.conn.start_session()

        try:
            # TODO consider getting notification xpaths from each commands' classmethod
            self.notif_session.subscribe_notification_tree(
                "goldstone-tai", "/goldstone-tai:*", 0, 0, self.notification_cb
            )
            self.notif_session.subscribe_notification_tree(
                "goldstone-onlp", "/goldstone-onlp:*", 0, 0, self.notification_cb
            )
            self.notif_session.subscribe_notification_tree(
                "goldstone-interfaces",
                "/goldstone-interfaces:*",
                0,
                0,
                self.notification_cb,
            )
        except sr.SysrepoNotFoundError as e:
            logger.warning(f"mgmt daemons not running?: {e}")

    def disable_notification(self):
        if not self.notif_session:
            logger.warning("notification already disabled")
            return
        self.notif_session.stop()
        self.notif_session = None

    def notification_cb(self, a, b, c, d):
        print(b.print_dict())

    def __str__(self):
        return ""


class GoldstoneShellCompleter(Completer):
    def __init__(self, context):
        self.context = context

    def get_completions(self, document, complete_event):
        return self.context.completion(document, complete_event)


class GoldstoneShell(object):
    def __init__(self, sess=None, default_prompt="> ", prefix=""):
        if sess == None:
            for i in range(10):
                try:
                    conn = sr.SysrepoConnection()
                except sr.errors.SysrepoSysError as e:
                    logger.warn(
                        f"failed to establish sysrepo connection: {e} retrying ({i}/10)"
                    )
                    time.sleep(0.1)
                else:
                    break
            else:
                stdout.error("failed to establish sysrepo connection")
                sys.exit(1)

        sess = conn.start_session()
        self.context = Root(conn)

        self.completer = GoldstoneShellCompleter(self.context)
        self.default_input = ""
        self.default_prompt = default_prompt
        self.prefix = prefix

        # TODO subscribe to global error message bus

    def prompt(self):
        c = self.context
        l = [str(c)]
        while c.parent:
            l.insert(0, str(c.parent))
            c = c.parent
        return (
            self.prefix + ("/".join(l)[1:] if len(l) > 1 else "") + self.default_prompt
        )

    async def exec(self, cmd: list, no_fail=True):
        ret = await self.context.exec_async(cmd, no_fail=no_fail)
        if ret:
            self.context = ret
            self.completer.context = ret
        self.default_input = ""

    def bindings(self):
        b = KeyBindings()

        @b.add("?")
        def _(event):
            buf = event.current_buffer
            original_text = buf.text
            help_msg = event.app.shell.context.help(buf.text)
            buf.insert_text("?")
            buf.insert_line_below(copy_margin=False)
            buf.insert_text(help_msg)
            event.app.exit("")
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


async def loop_async(shell):
    session = PromptSession()

    with patch_stdout.patch_stdout():
        while True:
            c = shell.completer
            p = shell.prompt()
            b = shell.bindings()
            session.app.shell = shell
            try:
                line = await session.prompt_async(
                    p, completer=c, key_bindings=b, default=shell.default_input
                )
            except KeyboardInterrupt:
                print("Execute 'exit' to exit")
                continue

            if len(line) > 0:
                await shell.exec(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--command-string")
    parser.add_argument("-k", "--keep-open", action="store_true")
    parser.add_argument("-x", "--stdin", action="store_true")
    args = parser.parse_args()

    formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)-5s][%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    if args.verbose:
        console.setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG)
        sr.configure_logging(py_logging=True)
        logging.getLogger("sysrepo").setLevel(logging.INFO)

    console.setFormatter(formatter)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    shf = logging.Formatter("%(message)s")
    sh.setFormatter(shf)

    stdout.setLevel(logging.DEBUG)
    stdout.addHandler(sh)

    shell = GoldstoneShell()

    async def _main():

        if args.stdin or args.command_string:
            stream = sys.stdin if args.stdin else args.command_string.split(";")
            for line in stream:
                try:
                    await shell.exec(line, no_fail=False)
                except CLIException as e:
                    stdout.info("failed to execute: {}".format(line))
                    stdout.info(e)
                    sys.exit(1)
            if not args.keep_open:
                return

        tasks = [loop_async(shell)]

        try:
            await asyncio.gather(*tasks)
        except BreakLoop:
            return

    asyncio.run(_main())


if __name__ == "__main__":
    main()
