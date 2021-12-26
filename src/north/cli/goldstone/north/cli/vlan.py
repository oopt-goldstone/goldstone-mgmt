from .base import Command, InvalidInput
from .cli import (
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root

import sysrepo as sr
import libyang as ly
from tabulate import tabulate
from natsort import natsorted
from .common import sysrepo_wrap, print_tabular

from .interface import InterfaceContext

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-vlan:vlans/vlan"


def get_session(cmd):
    return cmd.context.root().conn.start_session()


def vlan_xpath(vid):
    return f"{XPATH}[vlan-id='{vid}']"


def get_vids(session):
    sr_op = sysrepo_wrap(session)
    xpath = "/goldstone-vlan:vlans/vlan/vlan-id"
    try:
        data = sr_op.get_data(xpath)
    except sr.SysrepoNotFoundError:
        return []
    data = ly.xpath_get(data, xpath)
    return [str(v) for v in data]


def get_interface_mode(session, ifname):
    sr_op = sysrepo_wrap(session)
    xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode"
    mode = sr_op.get_data(xpath)
    return ly.xpath_get(mode, xpath).lower()


def show_vlans(session, details="details"):
    sr_op = sysrepo_wrap(session)

    try:
        data = sr_op.get_data(XPATH, "operational")
    except sr.SysrepoNotFoundError:
        stderr.info("no vlan configured")
        return
    except sr.SysrepoCallbackFailedError as e:
        raise InvalidInput(e.details[0][1] if e.details else str(e))

    data = ly.xpath_get(data, XPATH)
    rows = []
    for v in data:
        vid = v.get("vlan-id", "-")
        name = v["state"].get("name", "-")
        members = natsorted(v.get("members", {}).get("member", []))
        modes = []
        for ifname in members:
            modes.append(get_interface_mode(session, ifname))

        members = "\n".join(members) if len(members) > 0 else "-"
        modes = "\n".join(modes) if len(modes) > 0 else "-"

        rows.append((vid, name, members, modes))

    rows = natsorted(rows, lambda v: v[0])
    stdout.info(tabulate(rows, ["vid", "name", "members", "mode"]))


def set_name(session, vid, name):
    sr_op = sysrepo_wrap(session)
    sr_op.set_data(f"{vlan_xpath(vid)}/config/name", name)


def create(session, vids: int | list[int]):
    sr_op = sysrepo_wrap(session)
    if type(vids) == int:
        vids = [vids]

    for vid in vids:
        sr_op.set_data(f"{vlan_xpath(vid)}/config/vlan-id", vid, no_apply=True)
    sr_op.apply()


def delete(session, vids: int | list[int]):
    sr_op = sysrepo_wrap(session)
    if type(vids) == int:
        vids = [vids]

    for vid in vids:
        if str(vid) not in get_vids(session):
            raise InvalidInput(f"vlan {vid} not found")
        sr_op.delete_data(vlan_xpath(vid), no_apply=True)
    sr_op.apply()


def show(session, vid):
    xpath = vlan_xpath(vid)
    sr_op = sysrepo_wrap(session)
    v = sr_op.get_data(xpath, "operational")
    v = ly.xpath_get(v, xpath)
    rows = [("vid", v.get("vlan-id", "-"))]
    rows.append(("name", v["state"].get("name", "-")))
    members = natsorted(v.get("members", {}).get("member", []))
    members = "\n".join(f"{m} {get_interface_mode(session, m)}" for m in members)
    rows.append(("members", members))
    stdout.info(tabulate(rows))


def run_conf(session):
    for vid in get_vids(session):
        stdout.info(f"vlan {vid}")
        stdout.info(f"  quit")
    stdout.info("!")


def set_vlan_mem(session, ifnames, mode, vid, config=True, no_apply=False):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        prefix = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
        xpath = prefix + "/config"
        sr_op.set_data(f"{xpath}/name", ifname, no_apply=True)
        xpath = prefix + "/goldstone-vlan:switched-vlan/config"

        if config:
            sr_op.set_data(f"{xpath}/interface-mode", mode.upper(), no_apply=True)
            if mode == "access":
                sr_op.set_data(f"{xpath}/access-vlan", vid, no_apply=True)
            else:
                sr_op.set_data(f"{xpath}/trunk-vlans", vid, no_apply=True)
        else:
            if mode == "access":
                sr_op.delete_data(f"{xpath}/access-vlan", no_apply=True)
            else:
                sr_op.delete_data(f"{xpath}/trunk-vlans[.='{vid}']", no_apply=True)

    if not no_apply:
        sr_op.apply()


def parse_vlan_range(r: str) -> list[int]:
    vids = []
    for vlans in r.split(","):
        vlan_limits = vlans.split("-")
        if vlans.isdigit():
            vids.append(int(vlans))
        elif (
            len(vlan_limits) == 2
            and vlan_limits[0].isdigit()
            and vlan_limits[1].isdigit()
            and vlan_limits[0] < vlan_limits[1]
        ):
            for vid in range(int(vlan_limits[0]), int(vlan_limits[1]) + 1):
                vids.append(vid)
        else:
            raise InvalidInput("invalid vlan range")
    return vids


class VLANContext(Context):
    def __init__(self, parent: None | Context, vid: str):
        self.vid_str = vid
        vids = parse_vlan_range(vid)
        super().__init__(parent)
        self.session = parent.root().conn.start_session()
        create(self.session, vids)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                for vid in vids:
                    show(self.session, vid)

        @self.command()
        def name(args):
            if len(args) != 1:
                raise InvalidInput("usage: name <name>")
            if len(vids) > 1:
                raise InvalidInput("can't set name. multiple vlans are selected")
            set_name(self.session, vids[0], args[0])

    def __str__(self):
        return "vlan({})".format(self.vid_str)


class Show(Command):
    COMMAND_DICT = {
        "details": Command,
    }

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        return show_vlans(get_session(self), line[0])

    def usage(self):
        return "[ details ]"


GlobalShowCommand.register_command("vlan", Show, when=ModelExists("goldstone-vlan"))


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return run_conf(get_session(self))
        else:
            stderr.info(self.usage())


RunningConfigCommand.register_command("vlan", Run, when=ModelExists("goldstone-vlan"))


class TechSupport(Command):
    def exec(self, line):
        show_vlans(get_session(self))
        self.parent.xpath_list.append("/goldstone-vlan:vlans")


TechSupportCommand.register_command(
    "vlan", TechSupport, when=ModelExists("goldstone-vlan")
)


class VLANCommand(Command):
    COMMAND_DICT = {}

    def arguments(self):
        return ["range"] + get_vids(get_session(self))

    def usage(self):
        return "{ <vlan-id> | range <range-list> }"

    def exec(self, line):
        if len(line) not in [1, 2]:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        if self.parent and self.parent.name == "no":
            if len(line) == 1 and line[0].isdigit():
                delete(get_session(self), int(line[0]))
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: {self.name_all()} range <range-list>")
                vids = parse_vlan_range(line[1])
                delete(get_session(self), vids)
            else:
                raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        else:
            if len(line) == 1:
                return VLANContext(self.context, line[0])
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: {self.name_all()} range <range-list>")
                return VLANContext(self.context, line[1])
            else:
                raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")


Root.register_command(
    "vlan",
    VLANCommand,
    when=ModelExists("goldstone-vlan"),
    add_no=True,
    no_completion_on_exec=True,
)


class SwitchportModeVLANCommand(Command):
    def arguments(self):
        return get_vids(self.context.session)


class SwitchportModeAccessCommand(Command):
    COMMAND_DICT = {"vlan": SwitchportModeVLANCommand}


class SwitchportModeTrunkCommand(Command):
    COMMAND_DICT = {"vlan": SwitchportModeVLANCommand}


class SwitchportModeCommand(Command):
    COMMAND_DICT = {
        "access": SwitchportModeAccessCommand,
        "trunk": SwitchportModeTrunkCommand,
    }

    def exec(self, line):
        if len(line) < 3 or (line[0] not in self.COMMAND_DICT) or (line[1] != "vlan"):
            raise InvalidInput(f"usage : {self.name_all()} [trunk|access] vlan <vid>")

        set_vlan_mem(
            get_session(self),
            self.context.ifnames,
            line[0],
            line[2],
            config=self.root.name != "no",
        )


class SwitchportCommand(Command):
    COMMAND_DICT = {"mode": SwitchportModeCommand}


InterfaceContext.register_command(
    "switchport", SwitchportCommand, when=ModelExists("goldstone-vlan"), add_no=True
)
