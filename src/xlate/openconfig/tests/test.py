"""Unittest runner for OpenConfig translators."""


import unittest
import sys


if __name__ == "__main__":
    sys.path.insert(0, "../../../lib/")
    sys.path.insert(0, "../")
    testsuite = unittest.TestLoader().discover(".")
    unittest.TextTestRunner().run(testsuite)
