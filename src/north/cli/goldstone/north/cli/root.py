import sysrepo as sr
from libyang import SNode
import subprocess
import logging

from .base import InvalidInput, Command, CLIException
from .cli import Context

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

        with self.context.conn.start_session() as sess:
            sess.switch_datastore("startup")

            if line[0] == "all":
                ctx = self.context.conn.get_ly_ctx()
                modules = [m.name() for m in ctx if "goldstone" in m.name()]
            else:
                modules = [line[0]]

            for m in modules:
                try:
                    stdout.info(f"saving module {m}")
                    sess.copy_config("running", m)
                except sr.SysrepoError as e:
                    raise CLIException(f"failed to save {m}: {e}")

    def arguments(self):
        ctx = self.context.conn.get_ly_ctx()
        cmds = [m.name() for m in ctx if "goldstone" in m.name()]
        cmds.append("all")
        return cmds


class Root(Context):
    REGISTERED_COMMANDS = {}

    def __init__(self, conn=None):
        if conn == None:
            conn = sr.SysrepoConnection()
        self.conn = conn
        self.notif_session = None
        ctx = self.conn.get_ly_ctx()
        self.installed_modules = [m.name() for m in ctx]

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
        self.notif_session = self.conn.start_session("running")
        ctx = self.conn.get_ly_ctx()
        for model in ctx:
            if "goldstone" not in model.name():
                continue

            module = ctx.get_module(model.name())
            notif = list(module.children(types=(SNode.NOTIF,)))
            if len(notif) > 0:
                self.notif_session.subscribe_notification_tree(
                    model.name(), f"/{model.name()}:*", 0, 0, self.notification_cb
                )

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
