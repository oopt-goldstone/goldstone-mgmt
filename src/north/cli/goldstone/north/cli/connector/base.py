class CLIException(Exception):
    pass


class DSLocked(CLIException):
    def __init__(self, msg, what):
        self.msg = msg
        super().__init__(what)


class Node(object):
    pass


class Session(object):
    pass


class Connector(object):
    pass
