from .sysrepo import ServerConnector as SysrepoServerConnector
from goldstone.lib.errors import UnsupportedError


def create_server_connector(connector, module):
    if connector.type == "sysrepo":
        return SysrepoServerConnector(connector, module)
    else:
        raise UnsupportedError(
            f"creating a server-connector from {connector.type} is not supported"
        )
