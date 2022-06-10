from goldstone.lib.errors import UnsupportedError

import sys


class ServerConnector(object):
    @property
    def type(self):
        return "base"

    def send_notification(self, name: str, notification: dict):
        fname = sys._getframe().f_code.co_name
        raise UnsupportedError(f"{fname}() not supported by {self.type} connector")

    def subscribe_module_change(self, name, change_cb):
        fname = sys._getframe().f_code.co_name
        raise UnsupportedError(f"{fname}() not supported by {self.type} connector")

    def subscribe_oper_data_request(self, name, oper_cb):
        fname = sys._getframe().f_code.co_name
        raise UnsupportedError(f"{fname}() not supported by {self.type} connector")
