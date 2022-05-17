from .base import InvalidInput
from .cli import (
    Command,
    ConfigCommand,
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root
from .util import dig_dict

from tabulate import tabulate
from natsort import natsorted

from .interface import InterfaceContext

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-vlan:vlans/vlan"


def vlan_xpath(vid):
    return f"{XPATH}[vlan-id='{vid}']"


def get_vids(session):
    xpath = f"{XPATH}/vlan-id"
    return [str(v) for v in session.get(xpath, [])]


def get_interface_mode(session, ifname):
    xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode"
    return session.get(xpath, "").lower()


def show_vlans(session, details="details"):

    data = session.get_operational(XPATH)
    if data == None:
        stderr.info("no vlan configured")
        return

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
    session.set(f"{vlan_xpath(vid)}/config/name", name)
    session.apply()


def create(session, vids: int | list[int]):
    if type(vids) == int:
        vids = [vids]

    for vid in vids:
        session.set(f"{vlan_xpath(vid)}/config/vlan-id", vid)
    session.apply()


def delete(session, vids: int | list[int]):
    if type(vids) == int:
        vids = [vids]

    for vid in vids:
        if str(vid) not in get_vids(session):
            raise InvalidInput(f"vlan {vid} not found")
        session.delete(vlan_xpath(vid))
    session.apply()


def show(session, vid):
    xpath = vlan_xpath(vid)
    v = session.get_operational(xpath, one=True)
    rows = [("vid", v.get("vlan-id", "-"))]
    rows.append(("name", v["state"].get("name", "-")))
    members = natsorted(v.get("members", {}).get("member", []))
    members = "\n".join(f"{m} {get_interface_mode(session, m)}" for m in members)
    rows.append(("members", members))
    stdout.info(tabulate(rows))


def run_conf(session):
    n = 0
    for vid in get_vids(session):
        n += 2
        stdout.info(f"vlan {vid}")
        stdout.info(f"  quit")

    return n


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
        create(self.conn, vids)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                for vid in vids:
                    show(self.conn, vid)

        @self.command()
        def name(args):
            if len(args) != 1:
                raise InvalidInput("usage: name <name>")
            if len(vids) > 1:
                raise InvalidInput("can't set name. multiple vlans are selected")
            set_name(self.conn, vids[0], args[0])

    def __str__(self):
        return "vlan({})".format(self.vid_str)


class Show(Command):
    COMMAND_DICT = {
        "details": Command,
    }

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        return show_vlans(self.conn, line[0])

    def usage(self):
        return "[ details ]"


GlobalShowCommand.register_command("vlan", Show, when=ModelExists("goldstone-vlan"))


class Run(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())
        self.parent.num_lines = run_conf(self.conn)


RunningConfigCommand.register_command("vlan", Run, when=ModelExists("goldstone-vlan"))


class TechSupport(Command):
    def exec(self, line):
        show_vlans(self.conn)
        self.parent.xpath_list.append("/goldstone-vlan:vlans")


TechSupportCommand.register_command(
    "vlan", TechSupport, when=ModelExists("goldstone-vlan")
)


class VLANCommand(Command):
    COMMAND_DICT = {}

    def arguments(self):
        return ["range"] + get_vids(self.conn)

    def usage(self):
        return "{ <vlan-id> | range <range-list> }"

    def exec(self, line):
        if len(line) not in [1, 2]:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        if self.parent and self.parent.name == "no":
            if len(line) == 1 and line[0].isdigit():
                delete(self.conn, int(line[0]))
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: {self.name_all()} range <range-list>")
                vids = parse_vlan_range(line[1])
                delete(self.conn, vids)
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
        return get_vids(self.conn)


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

        mode = line[0]
        vid = line[2]

        for ifname in self.context.ifnames:
            prefix = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
            xpath = prefix + "/config"
            self.conn.set(f"{xpath}/name", ifname)
            xpath = prefix + "/goldstone-vlan:switched-vlan/config"

            if self.root.name != "no":
                self.conn.set(f"{xpath}/interface-mode", mode.upper())
                if mode == "access":
                    self.conn.set(f"{xpath}/access-vlan", vid)
                else:
                    self.conn.set(f"{xpath}/trunk-vlans", vid)
            else:
                if mode == "access":
                    self.conn.delete(f"{xpath}/access-vlan")
                else:
                    self.conn.delete(f"{xpath}/trunk-vlans[.='{vid}']")

        self.conn.apply()


class SwitchportCommand(ConfigCommand):
    COMMAND_DICT = {"mode": SwitchportModeCommand}

    def exec(self, line):
        raise InvalidInput(f"usage : {self.name_all()} mode [trunk|access] vlan <vid>")

    @classmethod
    def to_command(cls, conn, data, **options):
        config = dig_dict(data, ["switched-vlan", "config"])
        if not config:
            return

        mode = config.get("interface-mode", "").lower()
        if mode == "access":
            vids = [config["access-vlan"]]
        elif mode == "trunk":
            vids = config.get("trunk-vlans", [])
        else:
            return

        return [f"switchport mode {mode} vlan {vid}" for vid in vids]


InterfaceContext.register_command(
    "switchport", SwitchportCommand, when=ModelExists("goldstone-vlan"), add_no=True
)
