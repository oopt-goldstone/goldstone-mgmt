import logging

from goldstone.lib.connector.sysrepo import Connector

logger = logging.getLogger(__name__)


class MockConnector(Connector):
    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        if ds != "operational":
            return super().get(
                xpath,
                default,
                include_implicit_defaults,
                strip,
                one,
                ds,
            )

        oper_data = getattr(self, "oper_data", {})
        if isinstance(oper_data, Exception):
            raise oper_data
        logger.info(
            f"{xpath=}, {default=}, {include_implicit_defaults=}, {strip=}, {one=}, {ds=}"
        )
        return oper_data.get(xpath, default)
