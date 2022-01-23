class Error(Exception):
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
    pass
