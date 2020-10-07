
import sys
import os

from .base import Object, InvalidInput, Completer
from pyang import repository, context
from .sonic import Port, Vlan
import json
import libyang as ly
import sysrepo as sr
import base64


class sonic_wrap(Object):
    XPATH = '/'
    def __init__(self, conn, parent):
        self.session = conn.start_session()
        super(sonic_wrap, self).__init__(parent)
        self.vlan = Vlan(conn, self)
        self.port = Port(conn, self)
      
    def display(self, args):
        module = args[0]
        detail_level = args[1]
        if (module == 'vlan'):
            return (self.vlan.show(detail_level))
        elif (module == 'interface'):
            return (self.port.show(detail_level))

    def set_admin_status(self, xpath, status):
        self.set_param(xpath, 'admin_status', status)

    def set_param(self, xpath, param, value):
        v = value
        try:
            self.session.set_item('{}/{}'.format(xpath, param), v)
            self.session.apply_changes()
        except sr.errors.SysrepoCallbackFailedError as e:
            print(e)

 
        
