class Error(Exception):
    __slots__ = ("msg",)

    def __init__(self, msg: str):
        super().__init__()
        self.msg = msg

    def __str__(self):
        return self.msg

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.msg)


class InvalArgError(Error):
    pass


class NomemError(Error):
    pass


class NotFoundError(Error):
    pass


class InternalError(Error):
    pass


class UnsupportedError(Error):
    pass


class ValidationFailedError(Error):
    pass


class OperationFailedError(Error):
    pass


class UnauthorizedError(Error):
    pass


class LockedError(Error):
    pass


class TimeOutError(Error):
    pass


class LyError(Error):
    pass


class SysError(Error):
    pass


class ExistsError(Error):
    pass


class CallbackFailedError(Error):
    pass


class CallbackShelveError(Error):
    pass
