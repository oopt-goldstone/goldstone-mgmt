import sys
import os
import json
import logging

import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from tabulate import tabulate
from .base import InvalidInput, LockedError

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")

TIMEOUT_MS = 10000

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


class sysrepo_wrap(object):
    def __init__(self, session):
        self.session = session

    def get_data(
        self, xpath, ds="running", no_subs=False, include_implicit_values=True
    ):
        self.session.switch_datastore(ds)
        data = self.session.get_data(
            "{}".format(xpath),
            0,
            TIMEOUT_MS,
            no_subs=no_subs,
            include_implicit_defaults=include_implicit_values,
        )
        self.session.switch_datastore("running")
        return data

    def get_data_ly(self, xpath, ds="running", no_subs=False):
        self.session.switch_datastore(ds)
        data_ly = self.session.get_data_ly(
            "{}".format(xpath), 0, TIMEOUT_MS, no_subs=no_subs
        )
        self.session.switch_datastore("running")
        return data_ly

    def set_data(self, xpath, value, ds="running"):
        self.session.switch_datastore(ds)
        try:
            self.session.set_item(xpath, value)
            self.session.apply_changes(wait=True)
        except (
            sr.errors.SysrepoCallbackFailedError,
            sr.errors.SysrepoValidationFailedError,
        ) as error:
            self.session.discard_changes()
            raise InvalidInput(str(error))
        except sr.errors.SysrepoInvalArgError as error:
            msg = str(error)
            msg = msg.split("(")[0]
            raise InvalidInput(msg)
        except sr.errors.SysrepoLockedError as error:
            raise LockedError(f"{xpath} is locked", error)
        self.session.switch_datastore("running")

    def delete_data(self, xpath, ds="running"):
        self.session.switch_datastore(ds)
        try:
            self.session.delete_item(xpath)
            self.session.apply_changes(wait=True)
        except (
            sr.errors.SysrepoCallbackFailedError,
            sr.errors.SysrepoValidationFailedError,
        ) as error:
            raise InvalidInput(str(error))
        except sr.errors.SysrepoInvalArgError as error:
            msg = str(error)
            msg = msg.split("(")[0]
            raise InvalidInput(msg)
        except sr.errors.SysrepoLockedError as error:
            raise LockedError(f"{xpath} is locked", error)
        self.session.switch_datastore("running")

    def get_leaf_data(self, xpath, attr, ds="running"):
        self.session.switch_datastore("operational")
        val_list = []
        try:
            items = self.session.get_items("{}/{}".format(xpath, attr))
            for item in items:
                val_list.append(item.value)
        except (
            sr.errors.SysrepoCallbackFailedError,
            sr.errors.SysrepoValidationFailedError,
        ) as error:
            raise InvalidInput(str(error))
        except sr.errors.SysrepoInvalArgError as error:
            msg = str(error)
            msg = msg.split("(")[0]
            raise InvalidInput(msg)
        self.session.switch_datastore("running")
        return val_list
