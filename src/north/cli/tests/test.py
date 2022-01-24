import unittest
from unittest import mock
import sysrepo
from goldstone.north.cli.root import Root
from goldstone.lib.connector.sysrepo import Connector
import itertools
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
import os
import json
import sys

logger = logging.getLogger(__name__)

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)


class MockConnector(Connector):
    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        if ds != "operational":
            return super().get(
                xpath, default, include_implicit_defaults, strip, one, ds
            )

        oper_data = getattr(self, "oper_data", {})
        logger.info(
            f"{xpath=}, {default=}, {include_implicit_defaults=}, {strip=}, {one=}, {ds=}"
        )
        return oper_data.get(xpath, default)


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

    async def test_show_interface_brief(self):
        from goldstone.north.cli import interface

        conn = MockConnector()
        root = Root(conn)
        data = [
            {
                "name": "Interface0",
                "state": {"oper-status": "UP", "admin-status": "UP"},
            },
            {
                "name": "Interface1",
                "state": {"oper-status": "DOWN", "admin-status": "UP"},
            },
            {
                "name": "Interface2",
                "state": {"oper-status": "DOWN"},
            },
            {
                "name": "Interface3",
                "state": {"admin-status": "UP"},
            },
        ]

        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface": data,
        }
        logger = logging.getLogger("stdout")

        with self.assertLogs(logger=logger) as l:
            root.exec("show interface brief")
            lines = l.records[0].msg.split("\n")
            for i, line in enumerate(lines[3:-1]):
                elems = [e.strip() for e in line.split("|") if e]
                self.assertEqual(elems[0], data[i]["name"])
                self.assertEqual(
                    elems[1], data[i]["state"].get("oper-status", "-").lower()
                )
                self.assertEqual(
                    elems[2], data[i]["state"].get("admin-status", "-").lower()
                )
