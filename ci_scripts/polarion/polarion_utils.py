import logging
import re
import shlex
import subprocess


logging.basicConfig(level=logging.INFO)

LOGGER = logging.getLogger(__name__)
PROJECT = "CNV"


def find_polarion_ids(data):
    match_ids = set()
    for item in data:
        match = re.findall(rf"pytest.mark.polarion.*{PROJECT}-[0-9]+", item)
        if match:
            match_id = re.findall(rf"{PROJECT}-[0-9]+", match[0])
            match_ids.add(match_id[0])

    return match_ids


def git_diff():
    data = subprocess.check_output(shlex.split("git diff HEAD^-1"))
    data = data.decode("utf-8")
    return data


def git_diff_added_removed_lines():
    diff = {}
    for line in git_diff().splitlines():
        if line.startswith("+"):
            diff.setdefault("added", []).append(line)

        if line.startswith("-"):
            diff.setdefault("removed", []).append(line)

    return diff


def get_polarion_ids_from_diff(diff):
    added_ids = find_polarion_ids(data=diff.get("added", []))
    removed_ids = find_polarion_ids(data=diff.get("removed", []))
    return added_ids, removed_ids
