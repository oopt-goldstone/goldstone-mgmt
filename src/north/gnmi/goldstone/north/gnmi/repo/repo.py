"""Repository interface."""


class NotFoundError(Exception):
    def __init__(self, item):
        self.item = item
        super().__init__("{}: Item not found".format(self.item))


class ApplyFailedError(Exception):
    def __init__(self):
        super().__init__("Apply changes to the repository failed")


class Repository:
    """Repository interface.

    Repository is a abstract class of a system data repository. You should not use this directly. You can use a
    concrete class that is implemented for the datastore (e.g. Sysrepo, Redis) instead. Concrete classes may have
    their own attributes.
    """

    def start(self):
        """Start a connection/session."""
        pass

    def stop(self):
        """Stop a connection/session.

        All reserved resources that the connection/session has will be released."""
        pass

    def get(self, xpath, strip=True):
        """Get a data tree from the xpath.

        Args:
            xpath (str): XPath to get.
            strip (bool): Return a tree without the prefix specified as xpath.

        Returns:
            dict: A data tree as a python dictionaly.

        Raises:
            NotFoundError: Matched data is not found.
            ValueError: 'xpath' is invalid.
        """
        pass

    def set(self, xpath, data):
        """Set a data to the xpath.

        If the item specified by the xpath already exists, update its value by the data. If not, create an item.

        This just registers a set change. You need to call apply() to apply the change to the repository.

        Args:
            xpath (str): Xpath to set.
            data (Any): Data to set. Structured types (e.g. list, dict) are not supported, you need to set() items one
              by one.

        Raises:
            ValueError: 'xpath' is invalid.
        """
        pass

    def delete(self, xpath):
        """Delete a data tree from the xpath.

        This just registers a delete change. You need to call apply() to apply the change to the repository.

        Args:
            xpath (str): Xpath to delete.

        Raises:
            NotFoundError: Matched data is not found.
            ValueError: 'xpath' is invalid.
        """
        pass

    def apply(self):
        """Apply all changes."""
        pass

    def discard(self):
        """Discard all changes that have not yet been applied."""
        pass

    def get_list_keys(self, path):
        """Get keys of container list.

        Args:
            path (str): Path to the contianer list.

        Raises:
            ValueError: 'path' has an invalid value.
        """
        pass
