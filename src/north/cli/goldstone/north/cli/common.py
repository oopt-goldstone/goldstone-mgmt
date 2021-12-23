import sys
import os
import json
import logging

import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from tabulate import tabulate
from .base import InvalidInput, CLIException

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

TIMEOUT_MS = 10000


class LockedError(CLIException):
    def __init__(self, msg, e):
        self.msg = msg
        self.e = e

    def __str__(self):
        return self.msg


# Function to print data from show command with tabulate library
def print_tabular(h, table_title=""):
    if table_title != "":
        stdout.info(f"\n{table_title}")

    table = []
    skip_attrs = ["index", "location"]
    for k, v in h.items():
        if k in skip_attrs:
            continue
        table.append([k, v])

    stdout.info(tabulate(table))


def wrap_sysrepo_error(func):
    def f(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except sr.SysrepoError as error:
            sess = args[0].session
            sess.discard_changes()
            raise InvalidInput(error.details[0][1])
        except sr.errors.SysrepoLockedError as error:
            sess = args[0].session
            sess.discard_changes()
            raise LockedError(f"{xpath} is locked", error)

    return f


class sysrepo_wrap(object):
    def __init__(self, session):
        self.session = session

    def get_data(self, xpath, ds="running", include_implicit_values=True):
        self.session.switch_datastore(ds)
        data = self.session.get_data(
            xpath,
            0,
            TIMEOUT_MS,
            include_implicit_defaults=include_implicit_values,
        )
        self.session.switch_datastore("running")
        return data

    @wrap_sysrepo_error
    def set_data(self, xpath, value, ds="running", no_apply=False):
        self.session.switch_datastore(ds)
        self.session.set_item(xpath, value)
        if not no_apply:
            self.session.apply_changes(wait=True)
        self.session.switch_datastore("running")

    @wrap_sysrepo_error
    def delete_data(self, xpath, ds="running", no_apply=False):
        self.session.switch_datastore(ds)
        self.session.delete_item(xpath)
        if not no_apply:
            self.session.apply_changes(wait=True)
        self.session.switch_datastore("running")

    @wrap_sysrepo_error
    def get_leaf_data(self, xpath, attr, ds="running"):
        self.session.switch_datastore(ds)
        items = self.session.get_items("{}/{}".format(xpath, attr))
        self.session.switch_datastore("running")
        return [item.value for item in items]

    @wrap_sysrepo_error
    def apply(self):
        self.session.apply_changes(wait=True)

    @wrap_sysrepo_error
    def discard_changes(self):
        self.session.discard_changes()
