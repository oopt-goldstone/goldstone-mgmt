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
from natsort import natsorted

from .base import InvalidInput, BreakLoop, Command, CLIException
from .cli import GSObject as Object
from .tai_cli import Transponder
from .sonic_cli import Interface, Vlan, Ufd, Portchannel
from . import sonic
from .system_cli import AAA_CLI, TACACS_CLI, ManagementInterface, System
from .system import AAA, TACACS, Mgmtif

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

        super().__init__(None, fuzzy_completion=True)

        self.ufd = sonic.UFD(conn)
        self.portchannel = sonic.Portchannel(conn)
        self.vlan = sonic.Vlan(conn)
        self.port = sonic.Port(conn)

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
            "vlan": FuzzyWordCompleter(
                lambda: ["range"] + self.vlan.get_vids(), WORD=True
            ),
            "aaa": {"authentication": {"login": None}},
            "tacacs-server": {"host": None},
            "ufd": FuzzyWordCompleter(self.ufd.get_id, WORD=True),
            "portchannel": FuzzyWordCompleter(self.portchannel.get_id, WORD=True),
        }
        # TODO:add timer for inactive user

        self.add_command(SetCommand(self, name="set"))
        self.add_command(SaveCommand(self, name="save"))

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
        def system(line):
            if len(line) != 0:
                raise InvalidInput("usage: system[cr]")
            return System(conn, self)

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

        @self.command(FuzzyWordCompleter(get_ifnames, WORD=True))
        def interface(line):
            if len(line) != 1:
                raise InvalidInput("usage: interface <ifname>")
            return Interface(conn, self, line[0])

        @self.command(
            FuzzyWordCompleter(self.get_mgmt_ifname, WORD=True),
            name="management-interface",
        )
        def management_interface(line):
            if len(line) != 1:
                raise InvalidInput("usage: management-interface <ifname>")
            return ManagementInterface(conn, self, line[0])

        @self.command(FuzzyWordCompleter(self.ufd.get_id, WORD=True))
        def ufd(line):
            if len(line) != 1:
                raise InvalidInput("usage: ufd <ufd-id>")
            return Ufd(conn, self, line[0])

        @self.command(FuzzyWordCompleter(self.portchannel.get_id, WORD=True))
        def portchannel(line):
            if len(line) != 1:
                raise InvalidInput("usage: portchannel <portchannel_id>")
            return Portchannel(conn, self, line[0])

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
            stdout.info(self.session.rpc_send("/goldstone-system:reboot", {}))

        @self.command()
        def shutdown(line):
            stdout.info(self.session.rpc_send("/goldstone-system:shutdown", {}))

        # SYSTEM CLIs  -- END

        def isValidVlanRange(Range):
            for vlans in Range.split(","):
                vlan_limits = vlans.split("-")
                if vlans.isdigit() or (
                    len(vlan_limits) == 2
                    and vlan_limits[0].isdigit()
                    and vlan_limits[1].isdigit()
                    and vlan_limits[0] < vlan_limits[1]
                ):
                    pass
                else:
                    return False
            return True

        @self.command(
            FuzzyWordCompleter(lambda: (["range"] + self.vlan.get_vids()), WORD=True),
        )
        def vlan(line):
            if len(line) not in [1, 2]:
                raise InvalidInput("usage: vlan <vlan-id>")
            if len(line) == 1 and line[0].isdigit():
                return Vlan(conn, self, line[0])
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: vlan range <range-list>")
                elif isValidVlanRange(line[1]):
                    for vlans in line[1].split(","):
                        if vlans.isdigit():
                            self.vlan.create(vlans)
                        else:
                            vlan_limits = vlans.split("-")
                            for vid in range(
                                int(vlan_limits[0]), int(vlan_limits[1]) + 1
                            ):
                                self.vlan.create(str(vid))

                else:
                    stderr.info("The vlan-range entered is invalid")
            else:
                stderr.info("The vlan-id entered must be numbers and not letters")

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(line):
            if len(line) == 2:
                if line[0] == "vlan":
                    self.vlan.delete(line[1])
                elif line[0] == "ufd":
                    self.ufd.delete(line[1])
                elif line[0] == "portchannel":
                    self.portchannel.delete(line[1])
                else:
                    raise InvalidInput(self.no_usage())
            elif len(line) == 3:
                if line[0] == "aaa":
                    if line[1] == "authentication" and line[2] == "login":
                        self.aaa_sys.set_no_aaa()
                    else:
                        stderr.info("Enter the valid no command for aaa")
                elif line[0] == "tacacs-server":
                    if line[1] == "host":
                        self.tacacs_sys.set_no_tacacs(line[2])
                    else:
                        stderr.info("Enter valid no command for tacacs-server")
                elif line[0] == "vlan" and line[1] == "range":
                    if isValidVlanRange(line[2]):
                        vlan_list = self.vlan.get_vids()
                        for vlans in line[2].split(","):
                            if vlans.isdigit():
                                if vlans in vlan_list:
                                    self.vlan.delete(vlans)
                            else:
                                vlan_limits = vlans.split("-")
                                for vid in range(
                                    int(vlan_limits[0]), int(vlan_limits[1]) + 1
                                ):
                                    if str(vid) in vlan_list:
                                        self.vlan.delete(str(vid))
                    else:
                        stderr.info("Enter a valid range for vlan")

                else:
                    raise InvalidInput(self.no_usage())
            else:
                raise InvalidInput(self.no_usage())

    def get_mgmt_ifname(self):
        return [v["name"] for v in self.mgmt.get_mgmt_interface_list("operational")]

    def get_modules(self):
        path = "/goldstone-tai:modules/module/name"
        self.session.switch_datastore("operational")
        d = self.session.get_data(path)
        return natsorted(v["name"] for v in d["modules"]["module"])

    def date(self, line):
        date = " ".join(["date"] + line)
        subprocess.call(date, shell=True)

    def no_usage(self):
        return (
            "usage:\n"
            "no vlan <vid>\n"
            "no vlan range <range>\n"
            "no aaa authentication login\n"
            "no tacacs-server host <address>\n"
            "no ufd <ufd-id>\n"
            "no portchannel <portchannel-id>"
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
