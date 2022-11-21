import unittest
from goldstone.north.cli.main import main


class Test(unittest.TestCase):
    def test_main(self):
        main(["-c", "clear datastore all"])
