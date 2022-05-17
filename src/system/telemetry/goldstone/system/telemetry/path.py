"""Path manipulation utilities."""


import logging
import re
import libyang


logger = logging.getLogger(__name__)


class PathParser:
    """A path parser."""

    REGEX_PTN_LIST_KEY = re.compile(r"\[.*.*\]")

    def __init__(self, ctx):
        self._ctx = ctx

    def _is_container(self, data):
        return isinstance(data, dict)

    def _is_container_list(self, data):
        if isinstance(data, list):
            for elem in data:
                if isinstance(elem, dict):
                    return True
        return False

    def _find_head_node(self, path):
        return self._ctx.find_path(path)

    def _next_node(self, node, target_name):
        for child in list(node.children()):
            if child.name() == target_name:
                return child

    def _remove_list_keys(self, path):
        return re.sub(self.REGEX_PTN_LIST_KEY, "", path)

    def _find_node(self, path):
        path = self._remove_list_keys(path)
        path_elems = path.split("/")[1:]
        node = next(self._find_head_node("/" + path_elems[0]))
        for node_name in path_elems[1:]:
            node_name = node_name.split(":")[-1]
            node = self._next_node(node, node_name)
        return node

    def _get_list_keys(self, path):
        node = self._find_node(path)
        keys = []
        for key in node.keys():
            keys.append(key.name())
        return keys

    def _path_with_keys(self, container, path):
        keys_str = ""
        keys = self._get_list_keys(path)
        for key in keys:
            val = container[key]
            keys_str = f"{keys_str}[{key}='{val}']"
        return f"{path}{keys_str}"

    def _get_leaves(self, data, path, leaves):
        if self._is_container(data):
            for next_node, next_data in data.items():
                next_path = f"{path}/{next_node}"
                self._get_leaves(next_data, next_path, leaves)
        elif self._is_container_list(data):
            for container in data:
                next_path = self._path_with_keys(container, path)
                self._get_leaves(container, next_path, leaves)
        else:
            leaves[path] = data

    def _get_path_elems(self, path):
        return self._remove_list_keys(path).split("/")[1:]

    def _prune_leaves(self, leaves, path):
        path_elems = self._get_path_elems(path)
        sub_paths_to_delete = []
        for sub_path in leaves:
            sub_path_elems = self._get_path_elems(sub_path)
            if len(sub_path_elems) < len(path_elems):
                sub_paths_to_delete.append(sub_path)
                continue
            for index in range(len(path_elems)):
                if path_elems[index] != sub_path_elems[index]:
                    sub_paths_to_delete.append(sub_path)
                    break
        for sub_path in sub_paths_to_delete:
            try:
                del leaves[sub_path]
            except KeyError:
                continue

    def parse_dict_into_leaves(self, data, path):
        """Parse a data tree dictionaly into path to leaves.

        Args:
            data (dict): Data tree in dictionaly to parse.
            path (str): Path to the target node. It will be used to prune unnecessary leaves.

        Returns:
            dict: Parsed data.
              key: Path to a leaf node.
              value: Data of a leaf node.
        """
        dict_to_parse = {}
        top_prefix = self._get_path_elems(path)[0].split(":")[0]
        for key, value in data.items():
            new_key = top_prefix + ":" + key
            dict_to_parse[new_key] = value
        leaves = {}
        self._get_leaves(dict_to_parse, "", leaves)
        self._prune_leaves(leaves, path)
        return leaves

    def is_valid_path(self, path):
        """Validate a schema path.

        Args:
            path (str): Path to validate.

        Returns:
            bool: True for a valid path. False for a invalid path.
        """
        try:
            if self._find_node(path) is None:
                return False
        except libyang.LibyangError:
            return False
        return True
