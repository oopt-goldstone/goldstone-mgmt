#!/usr/bin/env python

import sysrepo as sr

import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import (
    Completer,
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
from natsort import natsorted

from .base import InvalidInput, BreakLoop, Command, CLIException
from .cli import GSObject as Object
from .tai_cli import Transponder
from .sonic_cli import Interface
from . import sonic
from .system_cli import ManagementInterface, System
from .system import Mgmtif

from .ufd import UFDCommand
from .vlan import VLANCommand
from .portchannel import PortchannelCommand

logger = logging.getLogger(__name__)

stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


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


class SaveCommand(Command):
    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name} [ <module name> | all ]")

        with self.context.conn.start_session() as sess:
            sess.switch_datastore("startup")

            if line[0] == "all":
                ctx = self.context.conn.get_ly_ctx()
                modules = [m.name() for m in ctx if "goldstone" in m.name()]
            else:
                modules = [line[0]]

            for m in modules:
                try:
                    stdout.info(f"saving module {m}")
                    sess.copy_config("running", m)
                except sr.SysrepoError as e:
                    raise CLIException(f"failed to save {m}: {e}")

    def list(self):
        ctx = self.context.conn.get_ly_ctx()
        cmds = [m.name() for m in ctx if "goldstone" in m.name()]
        cmds.append("all")
        return cmds


class Root(Object):
    XPATH = "/"

    def __init__(self, conn):
        self.conn = conn
        self.session = conn.start_session()
        self.notif_session = None
        ctx = self.conn.get_ly_ctx()
        self.installed_modules = [m.name() for m in ctx]

        super().__init__(None, fuzzy_completion=True)

        self.port = sonic.Port(conn)

        self.mgmt = Mgmtif(conn)

        self.add_command(SetCommand(self, name="set"))
        self.add_command(SaveCommand(self, name="save"))

        if "goldstone-uplink-failure-detection" in self.installed_modules:
            self.add_command(UFDCommand(self))
            self.no.add_sub_command("ufd", UFDCommand)

        if "goldstone-vlan" in self.installed_modules:
            self.add_command(VLANCommand(self))
            self.no.add_sub_command("vlan", VLANCommand)

        if "goldstone-portchannel" in self.installed_modules:
            self.add_command(PortchannelCommand(self))
            self.no.add_sub_command("portchannel", PortchannelCommand)

        if "goldstone-system" in self.installed_modules:

            @self.command()
            def system(line):
                if len(line) != 0:
                    raise InvalidInput("usage: system[cr]")
                return System(conn, self)

            @self.command(hidden=True)
            def reboot(line):
                stdout.info(self.session.rpc_send("/goldstone-system:reboot", {}))

            @self.command(hidden=True)
            def shutdown(line):
                stdout.info(self.session.rpc_send("/goldstone-system:shutdown", {}))

        if "goldstone-transponder" in self.installed_modules:

            @self.command(FuzzyWordCompleter(self.get_modules, WORD=True))
            def transponder(line):
                if len(line) != 1:
                    raise InvalidInput("usage: transponder <transponder name>")
                elif line[0] in self.get_modules():
                    return Transponder(conn, self, line[0])
                else:
                    stderr.info(f"There is no device of name {line[0]}")
                    return

        def get_ifnames():
            try:
                return self.port.interface_names()
            except Exception:
                return []

        if "goldstone-interfaces" in self.installed_modules:

            @self.command(FuzzyWordCompleter(get_ifnames, WORD=True))
            def interface(line):
                if len(line) != 1:
                    raise InvalidInput("usage: interface <ifname>")
                return Interface(conn, self, line[0])

        if "goldstone-mgmt-interfaces" in self.installed_modules:

            @self.command(
                FuzzyWordCompleter(self.get_mgmt_ifname, WORD=True),
                name="management-interface",
                hidden=True,  # hide it because not well implemented
            )
            def management_interface(line):
                if len(line) != 1:
                    raise InvalidInput("usage: management-interface <ifname>")
                return ManagementInterface(conn, self, line[0])

        @self.command()
        def ping(line):
            try:
                png = " ".join(["ping"] + line)
                subprocess.call(png, shell=True)
            except KeyboardInterrupt:
                stdout.info("")
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def traceroute(line):
            try:
                trct = " ".join(["traceroute"] + line)
                subprocess.call(trct, shell=True)
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def hostname(line):
            try:
                hst_name = " ".join(["hostname"] + line)
                subprocess.call(hst_name, shell=True)
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def date(line):
            self.date(line)

    def get_mgmt_ifname(self):
        return [v["name"] for v in self.mgmt.get_mgmt_interface_list("operational")]

    def get_modules(self):
        path = "/goldstone-transponder:modules/module/name"
        self.session.switch_datastore("operational")
        d = self.session.get_data(path)
        return natsorted(v["name"] for v in d["modules"]["module"])

    def date(self, line):
        date = " ".join(["date"] + line)
        subprocess.call(date, shell=True)

    def enable_notification(self):
        if self.notif_session:
            logger.warning("notification already enabled")
            return
        self.notif_session = self.conn.start_session()

        try:
            # TODO consider getting notification xpaths from each commands' classmethod
            self.notif_session.subscribe_notification_tree(
                "goldstone-transponder",
                "/goldstone-transponder:*",
                0,
                0,
                self.notification_cb,
            )
            self.notif_session.subscribe_notification_tree(
                "goldstone-platform",
                "/goldstone-platform:*",
                0,
                0,
                self.notification_cb,
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
        stdout.info(b.print_dict())

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
                stderr.error("failed to establish sysrepo connection")
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
                stderr.info("Execute 'exit' to exit")
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

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.DEBUG)
    shf = logging.Formatter("%(message)s")
    sh.setFormatter(shf)

    stdout.setLevel(logging.DEBUG)
    stdout.addHandler(sh)

    sh2 = logging.StreamHandler()
    sh2.setLevel(logging.DEBUG)
    sh2.setFormatter(shf)

    stderr.setLevel(logging.DEBUG)
    stderr.addHandler(sh2)

    shell = GoldstoneShell()

    async def _main():

        if args.stdin or args.command_string:
            stream = sys.stdin if args.stdin else args.command_string.split(";")
            for line in stream:
                try:
                    await shell.exec(line, no_fail=False)
                except CLIException as e:
                    stderr.info("failed to execute: {}".format(line))
                    stderr.info(e)
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
