import subprocess
import logging

from .base import InvalidInput
from .cli import Command, Context

logger = logging.getLogger(__name__)

stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class NotificationCommand(Command):
    COMMAND_DICT = {
        "enable": Command,
        "disable": Command,
    }

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(self.usage())

        if line[0] == "enable":
            self.context.enable_notification()
        else:
            self.context.disable_notification()

    def usage(self):
        return f"usage: {self.parent.name} {self.name} [enable|disable]"


class SetCommand(Command):
    COMMAND_DICT = {
        "notification": NotificationCommand,
    }


class SaveCommand(Command):
    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name} [ <module name> | all ]")

        if line[0] == "all":
            modules = [m for m in self.conn.models if "goldstone" in m]
        else:
            modules = [line[0]]

        for m in modules:
            conn.save(m)

    def arguments(self):
        cmds = [m for m in self.conn.models if "goldstone" in m]
        cmds.append("all")
        return cmds


class Root(Context):
    REGISTERED_COMMANDS = {}

    def __init__(self, conn):
        self.conn = conn
        self.notif_session = None

        super().__init__(None, fuzzy_completion=True)

        self.add_command("set", SetCommand)
        self.add_command("save", SaveCommand)

        @self.command()
        def ping(line):
            try:
                png = " ".join(["ping"] + line)
                subprocess.call(png, shell=True)
            except KeyboardInterrupt:
                stdout.info("")
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def traceroute(line):
            try:
                trct = " ".join(["traceroute"] + line)
                subprocess.call(trct, shell=True)
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def hostname(line):
            try:
                hst_name = " ".join(["hostname"] + line)
                subprocess.call(hst_name, shell=True)
            except:
                stderr.info("Unexpected error:", sys.exc_info()[0])

        @self.command()
        def date(line):
            self.date(line)

    def date(self, line):
        date = " ".join(["date"] + line)
        subprocess.call(date, shell=True)

    def enable_notification(self):
        if self.notif_session:
            logger.warning("notification already enabled")
            return
        self.notif_session = self.conn.new_session()
        for model in self.conn.models:
            if "goldstone" not in model:
                continue
            self.notif_session.subscribe_notifications(model, self.notification_cb)

    def disable_notification(self):
        if not self.notif_session:
            logger.warning("notification already disabled")
            return
        self.notif_session.stop()
        self.notif_session = None

    def notification_cb(self, a, b, c, d):
        stdout.info(b.print_dict())

    def __str__(self):
        return ""
