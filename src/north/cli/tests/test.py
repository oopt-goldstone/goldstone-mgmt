from gscli.base import Object, InvalidInput, Completer, Command
from prompt_toolkit.completion import WordCompleter
import unittest


class A(Command):
    def exec(self, line):
        return line

    def list(self):
        return ["Ethernet1_1", "Ethernet2_1"]


class Test(Object):
    def __init__(self):
        super().__init__(None, True)

        @self.command(WordCompleter(["a", "aaa", "b", "bbb"], sentence=True))
        def test(line):
            pass

        @self.command(WordCompleter(["a", "aaa", "b", "bbb"], sentence=True))
        def test2(line):
            pass

        self.add_command(A(self, name="a"), strict=False)


class TestCLI(unittest.TestCase):
    def test_basic_help(self):
        t = Test()
        self.assertEqual(t.help(""), "quit, exit, test, test2, a")
        self.assertEqual(t.help("t"), "test, test2")
        self.assertEqual(t.help("test "), "a, aaa, b, bbb")
        self.assertEqual(t.help("test a"), "a")
        self.assertEqual(t.help("test a "), "")
        self.assertEqual(t.help("a"), "a")
        self.assertEqual(t.help("a "), "Ethernet1_1, Ethernet2_1")
        self.assertEqual(
            t.help("a 2"), "Ethernet1_1, Ethernet2_1"
        )  # help show candidates when no match
        self.assertEqual(t.complete_input(["a", "2"], True), ["a", "Ethernet2_1"])
        self.assertEqual(t.exec("a A B C", no_fail=False), ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
