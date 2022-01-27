import sys


class Error(Exception):
    pass


class NotSupported(Error):
    pass


class DatastoreLocked(Error):
    def __init__(self, msg, what):
        self.msg = msg
        super().__init__(what)


class Node(object):
    pass


class Session(object):
    pass


class Connector(object):
    @property
    def type(self):
        raise "base"

    def new_session(self, ds):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    @property
    def models(self):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def find_node(self, xpath):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def save(self, model):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def rpc(self, xpath, args):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def set(self, xpath, value):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def delete(self, xpath):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def delete_all(self, model):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def apply(self):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def discard_changes(self):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):

        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def get_operational(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
    ):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")

    def get_startup(self, xpath):
        fname = sys._getframe().f_code.co_name
        raise NotSupported(f"{fname}() not supported by {self.type} connector")
