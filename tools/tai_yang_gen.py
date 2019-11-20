#!/usr/bin/env python

import sys

import clang.cindex
from clang.cindex import Index
from clang.cindex import Config
from optparse import OptionParser
from enum import Enum
from jinja2 import Environment

from tai import TAIHeader, TAIAttributeFlag

IGNORE_TYPE_LIST = ['tai_pointer_t', 'tai_notification_handler_t', 'tai_object_map_list_t', 'tai_attr_value_list_t']

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
            return '{} {};'.format(self.key, self.name)
        else:
            v = ['{} {} {{'.format(self.key, self.name)]
            v += [c.to_str() for c in self.children]
            v.append('}')
            return '\n'.join(v)

def shorten(v, typename):
    if not typename.endswith('_t'):
        raise Exception("invalid type name: {}".format(typename))
    t = typename[:-1].upper()
    if not v.startswith(t):
        raise Exception("invalid enum value name: {}".format(v))
    return v[len(t):].lower().replace('_', '-')

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('--clang-lib', default='/usr/lib/llvm-6.0/lib/libclang.so.1')
    (options, args) = parser.parse_args()

    Config.set_library_file(options.clang_lib)

    h = TAIHeader(args[0])

    m = Statement('module', 'goldstone-tai')
    k = Statement('yang-version', '"1.1"')
    m.add(k)
    m.add(Statement('namespace', '"http://goldstone.net/yang/tai"'))
    m.add(Statement('prefix', '"gs-tai"'))
    v = Statement('reference', '"0.1.0"')
    m.add(Statement('revision', '"2019-11-01"', [v]))

    for obj in h.objects:
        prefix = 'tai-' + obj.name.replace('_', '-')
        config  = Statement('grouping', prefix + '-config')
        state = Statement('grouping', prefix + '-state')

        m.add(config)
        m.add(state)

        config.add(Statement('leaf', 'name', Statement('type', 'string')))
        state.add(Statement('leaf', 'id', Statement('type', 'uint32')))
        state.add(Statement('leaf', 'description', Statement('type', 'string')))

        for attr in obj.get_attributes():

            if attr.type in IGNORE_TYPE_LIST:
                continue

            obj = attr.object_type
            objname = attr.object_name
            typename = attr.name
            prefix = 'TAI_{}_ATTR_'.format(objname.upper())
            shorttypename = typename[len(prefix):].lower().replace('_', '-')

            if TAIAttributeFlag.READ_ONLY in attr.flags:
                parent = state
            else:
                parent = config

            leaftype = 'leaf'

            if attr.enum_type:
                if attr.value_field == 's32list':
                    leaftype = 'leaf-list'
                type_ = Statement('type', 'enumeration')
                enum = h.get_enum(attr.enum_type)
                for v in enum.value_names():
                    n = shorten(v, enum.typename)
                    if n == 'max':
                        continue
                    type_.add(Statement('enum', n))
            elif attr.type == 'tai_char_list_t':
                type_ = Statement('type', 'string')
            elif attr.type == 'tai_int8_t':
                type_ = Statement('type', 'int8')
            elif attr.type == 'tai_int16_t':
                type_ = Statement('type', 'int16')
            elif attr.type == 'tai_int32_t':
                type_ = Statement('type', 'int32')
            elif attr.type == 'tai_int64_t':
                type_ = Statement('type', 'int64')
            elif attr.type == 'tai_uint8_t':
                type_ = Statement('type', 'uint8')
            elif attr.type == 'tai_uint16_t':
                type_ = Statement('type', 'uint16')
            elif attr.type == 'tai_uint32_t':
                type_ = Statement('type', 'uint32')
            elif attr.type == 'tai_uint64_t':
                type_ = Statement('type', 'uint64')
            elif attr.type == 'bool':
                type_ = Statement('type', 'boolean')
            elif attr.type == 'tai_float_t':
                # https://github.com/netmod-wg/yang-next/issues/34
                # we use IEEE float 32-bit encoding for BER
                if 'ber' in shorttypename:
                    type_ = Statement('type', 'binary')
                    type_.add(Statement('length', '"4"'))
                else:
                    type_ = Statement('type', 'decimal64')
                    type_.add(Statement('fraction-digits', 2))
            else:
                raise Exception('unhandled type: {}'.format(attr.type))

            leaf = Statement(leaftype, shorttypename)
            if 'brief' in attr.cmt:
                leaf.add(Statement('description', '"{}"'.format(attr.cmt['brief'])))
            leaf.add(type_)
            parent.add(leaf)

    def create_object(name):
        o = Statement('list', name)
        o.add(Statement('key', '"name"'))
        o.add(Statement('leaf', 'name', Statement('type', 'leafref', Statement('path', '"../config/name"'))))
        o.add(Statement('container', 'config', Statement('uses', 'tai-{}-config'.format(name))))
        o.add(Statement('container', 'state', [Statement('config', 'false'), Statement('uses', 'tai-{}-config'.format(name)), Statement('uses', 'tai-{}-state'.format(name))]))
        return o

    module = create_object('module')
    netif = create_object('network-interface')
    hostif = create_object('host-interface')

    module.add(netif)
    module.add(hostif)

    modules = Statement('container', 'modules', module)
    top = Statement('grouping', 'tai-component-top', modules)

    m.add(top)
    m.add(Statement('uses', 'tai-component-top'))

    print(m.to_str())
