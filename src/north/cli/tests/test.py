import sys
import os

sys.path.append('..')

from base import Object, InvalidInput, Completer
from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion

class TestCompleter(Completer):
    def __init__(self, word_dict):
        self.word_dict = word_dict

        super(TestCompleter, self).__init__(self.attrnames, self.valuenames)

    def attrnames(self):
        return self.word_dict.keys()

    def valuenames(self, attrname):
        return self.word_dict.get(attrname, [])

class Test(Object):

    def __init__(self):
        super(Test, self).__init__(None, None)

        @self.command(WordCompleter(['a', 'aaa', 'b', 'bbb'], sentence=True))
        def test(line):
            pass

        @self.command(TestCompleter({'a': ['1', '2', '3'], 'b': ['4', '5', '6']}))
        def test2(line):
            pass

        @self.command()
        def a(line):
            pass

if __name__ == '__main__':

    t = Test()

    assert(t.help('') == 'quit, test, test2, a')
    assert(t.help('t') == 'test, test2')
    assert(t.help('test ') == 'a, aaa, b, bbb')
    assert(t.help('test a') == 'a')
    assert(t.help('test a ') == '')
    assert(t.help('test2') == 'test2')
    assert(t.help('test2 ') == 'a, b')
    assert(t.help('test2 a') == 'a')
    assert(t.help('test2 a ') == '1, 2, 3')
    assert(t.help('test2 a 1') == '1')
    assert(t.help('test2 a 1 ') == '')
    assert(t.help('test2 a 1  ') == '')
    assert(t.help('a ') == '')
