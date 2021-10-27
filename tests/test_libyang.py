# https://github.com/CESNET/libyang/issues/937
import unittest
import libyang as ly


class TestLibYANG(unittest.TestCase):
    def test_enum(self):
        schema = """module a {
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
        }"""

        ctx = ly.Context()
        m = ctx.parse_module_str(schema)
        s = ctx.find_path("/a:test")
        t = list(s)[0]
        v = t.type().enums()
        self.assertEqual(len(list(v)), 4)
        for i, e in enumerate(t.type().enums()):
            self.assertEqual(e[0], (chr(ord("A") + i)))


if __name__ == "__main__":
    unittest.main()
