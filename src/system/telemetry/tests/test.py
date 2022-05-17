"""Unittest runner for a streaming telemetry server."""


import unittest
import sys


if __name__ == "__main__":
    sys.path.insert(0, "../../../lib/")
    sys.path.insert(0, "../")
    testsuite = unittest.TestLoader().discover(".")
    unittest.TextTestRunner(verbosity=2).run(testsuite)
