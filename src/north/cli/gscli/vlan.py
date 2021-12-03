from .base import Command, InvalidInput
from .cli import GSObject as Object
from .sonic import Vlan


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


class VLANObject(Object):
    def __init__(self, vlan: Vlan, parent: None | Object, vid: str):
        self.vid_str = vid
        vids = parse_vlan_range(vid)
        super().__init__(parent)
        vlan.create(vids)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            for vid in vids:
                vlan.show(vid)

        @self.command()
        def name(args):
            if len(args) != 1:
                raise InvalidInput("usage: name <name>")
            if len(vids) > 1:
                raise InvalidInput("can't set name. multiple vlans are selected")
            vlan.set_name(vids[0], args[0])

    def __str__(self):
        return "vlan({})".format(self.vid_str)


class VLANCommand(Command):
    SUBCOMMAND_DICT = {}

    def __init__(self, context: Object = None, parent: Command = None, name=None):
        if name == None:
            name = "vlan"
        super().__init__(context, parent, name)
        self.vlan = Vlan(context.root().conn)

    def list(self):
        return ["range"] + self.vlan.get_vids()

    def usage(self):
        return "<vlan-id> | range <range-list>"

    def exec(self, line):
        if len(line) not in [1, 2]:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        if self.parent and self.parent.name == "no":
            if len(line) == 1 and line[0].isdigit():
                self.vlan.delete(int(line[0]))
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: {self.name_all()} range <range-list>")
                vids = parse_vlan_range(line[1])
                self.vlan.delete(vids)
            else:
                raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        else:
            if len(line) == 1:
                return VLANObject(self.vlan, self.context, line[0])
            elif line[0] == "range":
                if len(line) != 2:
                    raise InvalidInput("usage: {self.name_all()} range <range-list>")
                return VLANObject(self.vlan, self.context, line[1])
            else:
                raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
