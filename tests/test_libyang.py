# https://github.com/CESNET/libyang/issues/937

import yang as ly

schema = '''module a {
    namespace "a";
    prefix "a";

    leaf test {
        type enumeration {
        enum A;
        enum B;
        enum C;
        enum D;
        }
    }
}'''

ctx = ly.Context()
ly.set_log_verbosity(ly.LY_LLDBG)
m = ctx.parse_module_mem(schema, ly.LYS_IN_YANG)
d = m.data()
s = d.find_path('/a:test')
t = s.schema()[0]
v = t.subtype()
if v.type().base() == ly.LY_TYPE_ENUM:
    enums = v.type().info().enums()
    count = enums.count()
    e = enums.enm()
    assert(count == len(e))
    for i in range(count):
        assert(e[i].name() == (chr(ord('A') + i)))
