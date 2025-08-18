import re
import shlex
from typing import TypedDict


class GuestDataCommandListType(TypedDict):
    name: str
    command: str
    regex: re.Pattern


VIRT_HANDLER_API_IDLE_STATE = 0.067

GUEST_DATA_RESULT_SEPARATOR = "|=====|"
GUEST_DATA_COMMAND_LIST: list[GuestDataCommandListType] = [
    {"name": "datetime", "command": "date -u -Is", "regex": re.compile(r"^(?P<datetime>.*)$")},
    {
        "name": "proc_stat",
        "command": "cat /proc/stat",
        "regex": re.compile(r".*\nbtime (?P<btime>[0-9]+)\n.*", re.DOTALL),
    },
    {
        "name": "uptime",
        "command": "uptime",
        "regex": re.compile(
            r"^(?P<current_time>[^ ]+) up (?P<up_for>[^,]+),[ ]+(?P<user_info>[^,]+),[ ]+"
            r"load average: (?P<load1min>[0-9]+\.[0-9]+), (?P<load5min>[0-9]+\.[0-9]+), (?P<load15min>[0-9]+\.[0-9]+)$"
        ),
    },
]
GUEST_DATA_COMMANDS = shlex.split(
    'sh -c "'
    + f" && echo '{GUEST_DATA_RESULT_SEPARATOR}' && ".join([str(entry["command"]) for entry in GUEST_DATA_COMMAND_LIST])
    + '"'
)
