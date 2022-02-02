#!/usr/bin/env python

import sys

import clang.cindex
from clang.cindex import Index
from clang.cindex import Config
from argparse import ArgumentParser
from enum import Enum
from jinja2 import Environment

from tai_meta_generator.main import TAIHeader, TAIAttributeFlag

IGNORE_TYPE_LIST = [
    "tai_pointer_t",
    "tai_object_map_list_t",
    "tai_attr_value_list_t",
    "tai_u32_range_t",
    "tai_u32_list_t",
    "tai_s16_list_t",
    "tai_u16_list_t",
    "tai_float_list_t",
]

IGNORE_ATTR_LIST = ["TAI_MODULE_ATTR_SCRIPT"]


class Statement(object):
    def __init__(self, key, name, c=[]):
        self.key = key
        self.name = name
        if type(c) != list:
            self.children = [c]
        else:
            self.children = c[:]

    def add(self, stmt):
        self.children.append(stmt)

    def to_str(self):
        if len(self.children) == 0:
            return "{} {};".format(self.key, self.name)
        else:
            v = ["{} {} {{".format(self.key, self.name)]
            v += [c.to_str() for c in self.children]
            v.append("}")
            return "\n".join(v)


def shorten(v, typename):
    if not typename.endswith("_t"):
        raise Exception("invalid type name: {}".format(typename))
    t = typename[:-1].upper()
    if not v.startswith(t):
        raise Exception("invalid enum value name: {}".format(v))
    return v[len(t) :].lower().replace("_", "-")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--clang-lib", default="/usr/lib/llvm-6.0/lib/libclang.so.1")
    parser.add_argument("header")
    parser.add_argument("custom", nargs="*", default=[])
    args = parser.parse_args()

    Config.set_library_file(args.clang_lib)

    h = TAIHeader(args.header)
    for c in args.custom:
        h.add_custom(c)

    m = Statement("module", "goldstone-transponder")
    k = Statement("yang-version", "1")
    m.add(k)
    m.add(Statement("namespace", '"http://goldstone.net/yang/transponder"'))
    m.add(Statement("prefix", '"gs-transponder"'))
    v = Statement("reference", '"0.1.0"')
    m.add(Statement("revision", '"2019-11-01"', [v]))

    notifications = []

    for obj in h.objects:
        objname = obj.name.replace("_", "-")
        prefix = "transponder-" + objname
        config = Statement("grouping", prefix + "-config")
        state = Statement("grouping", prefix + "-state")

        m.add(config)
        m.add(state)

        config.add(Statement("leaf", "name", Statement("type", "string")))
        state.add(Statement("leaf", "id", Statement("type", "uint64")))
        state.add(Statement("leaf", "description", Statement("type", "string")))

        for attr in obj.get_attributes():

            if attr.type in IGNORE_TYPE_LIST:
                continue

            if attr.name in IGNORE_ATTR_LIST:
                continue

            obj = attr.object_type
            objname = attr.object_name
            typename = attr.name
            prefix = "TAI_{}_ATTR_".format(objname.upper())
            shorttypename = typename[len(prefix) :].lower().replace("_", "-")

            if (
                attr.flags == None
                or TAIAttributeFlag.READ_ONLY in attr.flags
                or TAIAttributeFlag.CREATE_ONLY in attr.flags
            ):
                parent = state
            else:
                parent = config

            leaftype = "leaf"

            if attr.enum_type:
                if attr.value_field == "s32list":
                    leaftype = "leaf-list"
                type_ = Statement("type", "enumeration")
                enum = h.get_enum(attr.enum_type)
                for v in enum.value_names():
                    n = shorten(v, enum.typename)
                    if n == "max":
                        continue
                    type_.add(Statement("enum", n))
            elif attr.type == "tai_char_list_t":
                type_ = Statement("type", "string")
            elif attr.type == "tai_int8_t":
                type_ = Statement("type", "int8")
            elif attr.type == "tai_int16_t":
                type_ = Statement("type", "int16")
            elif attr.type == "tai_int32_t":
                type_ = Statement("type", "int32")
            elif attr.type == "tai_int64_t":
                type_ = Statement("type", "int64")
            elif attr.type == "tai_uint8_t":
                type_ = Statement("type", "uint8")
            elif attr.type == "tai_uint16_t":
                type_ = Statement("type", "uint16")
            elif attr.type == "tai_uint32_t":
                type_ = Statement("type", "uint32")
            elif attr.type == "tai_uint64_t":
                type_ = Statement("type", "uint64")
            elif attr.type == "bool":
                type_ = Statement("type", "boolean")
            elif attr.type == "tai_float_t":
                # https://github.com/netmod-wg/yang-next/issues/34
                # we use IEEE float 32-bit encoding for BER
                if "ber" in shorttypename:
                    type_ = Statement("type", "binary")
                    type_.add(Statement("length", '"4"'))
                else:
                    type_ = Statement("type", "decimal64")
                    type_.add(Statement("fraction-digits", 16))
            elif attr.type == "tai_notification_handler_t":
                type_ = Statement("type", "boolean")
                n = Statement(
                    "notification",
                    "{}-{}-event".format(objname.replace("_", "-"), shorttypename),
                )
                shorttypename = "enable-" + shorttypename
                keys = Statement("leaf-list", "keys")
                keys.add(Statement("type", "string"))
                keys.add(
                    Statement(
                        "description",
                        '"list of valid attribute name stored in the event"',
                    )
                )
                n.add(keys)
                n.add(Statement("leaf", "module-name", Statement("type", "string")))
                n.add(Statement("uses", config.name))
                n.add(Statement("uses", state.name))
                notifications.append(n)
            else:
                raise Exception("unhandled type: {}".format(attr.type))

            leaf = Statement(leaftype, shorttypename)
            if "brief" in attr.cmt:
                leaf.add(Statement("description", '"{}"'.format(attr.cmt["brief"])))
            leaf.add(type_)
            parent.add(leaf)

    def create_object(name):
        o = Statement("list", name)
        o.add(Statement("key", '"name"'))
        o.add(
            Statement(
                "leaf",
                "name",
                Statement("type", "leafref", Statement("path", '"../config/name"')),
            )
        )
        o.add(
            Statement(
                "container",
                "config",
                Statement("uses", "transponder-{}-config".format(name)),
            )
        )
        o.add(
            Statement(
                "container",
                "state",
                [
                    Statement("config", "false"),
                    Statement("uses", "transponder-{}-config".format(name)),
                    Statement("uses", "transponder-{}-state".format(name)),
                ],
            )
        )
        return o

    module = create_object("module")
    netif = create_object("network-interface")
    hostif = create_object("host-interface")

    module.add(netif)
    module.add(hostif)

    modules = Statement("container", "modules", module)
    top = Statement("grouping", "transponder-component-top", modules)

    m.add(top)
    m.add(Statement("uses", "transponder-component-top"))

    for n in notifications:
        m.add(n)

    print(m.to_str())
