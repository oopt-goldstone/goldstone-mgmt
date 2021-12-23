from goldstone.north.cli.base import Object, InvalidInput, Completer, Command
from prompt_toolkit.completion import WordCompleter, CompleteEvent
from prompt_toolkit.document import Document
import unittest


class A(Command):
    def exec(self, line):
        return line

    def arguments(self):
        return ["Ethernet1_1", "Ethernet2_1"]


class Test(Object):
    def __init__(self, fuzzy):
        super().__init__(None, fuzzy)

        @self.command(WordCompleter(["a", "aaa", "b", "bbb"], sentence=True))
        def test(line):
            pass

        @self.command(WordCompleter(["c", "cc", "b", "bbb2"], sentence=True))
        def test2(line):
            pass

        self.add_command("a", A)


class TestCLI(unittest.TestCase):
    def test_basic_help(self):
        t = Test(False)  # no fuzzy completion
        self.assertEqual(t.help(""), "quit, exit, test, test2, a")
        self.assertEqual(t.help("t"), "test, test2")
        self.assertEqual(t.help("t "), "")
        self.assertEqual(t.help("test"), "test, test2")
        self.assertEqual(t.help("test "), "a, aaa, b, bbb")
        self.assertEqual(t.help("test a"), "a, aaa")
        self.assertEqual(t.help("test a "), "")
        self.assertEqual(t.help("test2"), "test2")
        self.assertEqual(t.help("test2 "), "c, cc, b, bbb2")
        self.assertEqual(t.help("test2 b"), "b, bbb2")
        self.assertEqual(t.help("tes b"), "")
        self.assertEqual(t.help("2 b"), "")
        self.assertEqual(t.help("a"), "a")
        self.assertEqual(t.help("a "), "Ethernet1_1, Ethernet2_1")
        self.assertEqual(
            t.help("a 2"), "Ethernet1_1, Ethernet2_1"
        )  # help show candidates when no match
        self.assertEqual(
            t.exec("a Ethernet1_1 B C", no_fail=False), ["Ethernet1_1", "B", "C"]
        )

    def test_fuzzy_help(self):
        t = Test(True)  # fuzzy completion
        self.assertEqual(t.help(""), "quit, exit, test, test2, a")
        self.assertEqual(t.help("t"), "test, test2")
        self.assertEqual(t.help("es"), "test, test2")
        self.assertEqual(t.help("te"), "test, test2")
        self.assertEqual(t.help("2"), "test2")
        self.assertEqual(t.help("test2 b"), "b, bbb2")
        self.assertEqual(t.help("test2 2"), "bbb2")
        self.assertEqual(
            t.help("a 2"), "Ethernet2_1"
        )  # help show candidates when no match
        self.assertEqual(t.exec("a 2 B C", no_fail=False), ["Ethernet2_1", "B", "C"])


if __name__ == "__main__":
    unittest.main()
