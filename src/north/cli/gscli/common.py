import sys
import os
import json
import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from tabulate import tabulate


TIMEOUT_MS = 10000

# Function to print data from show command with tabulate library
def print_tabular(h, table_title):
    if table_title != "":
        print("\n", table_title, "\n")
    headers = ["Attribute Name", "Attribute Value"]
    upd_dict = {k: h[k] for k in h.keys() - {"index"}}
    attr = list(upd_dict.keys())
    rows = list(upd_dict.values())
    data = {headers[0]: attr, headers[1]: rows}
    print(tabulate(data, headers="keys", tablefmt="pretty"))


class sysrepo_wrap(object):
    def __init__(self):
        conn = sr.SysrepoConnection()
        self.session = conn.start_session()

    def get_data(self, xpath, ds="running", no_subs=False):
        self.session.switch_datastore(ds)
        data = self.session.get_data("{}".format(xpath), 0, TIMEOUT_MS, no_subs=no_subs)
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
            self.session.apply_changes()
        except sr.errors.SysrepoCallbackFailedError as e:
            print(e)
        except sr.errors.SysrepoInvalArgError as e:
            msg = str(e)
            msg = msg.split("(")[0]
            print(msg)
        self.session.switch_datastore("running")

    def delete_data(self, xpath, ds="running"):
        self.session.switch_datastore(ds)
        try:
            self.session.delete_item(xpath)
            self.session.apply_changes()
        except sr.errors.SysrepoValidationFailedError as e:
            msg = str(e)
            msg = msg.split(".,")[0]
            print(msg)
        self.session.switch_datastore("running")
