import os
from configparser import ConfigParser
from pathlib import Path


def get_connection_params():
    conf_file = os.path.join(Path(".").resolve(), "jira.cfg")
    parser = ConfigParser()
    # Open the file with the correct encoding
    parser.read(conf_file, encoding="utf-8")
    params_dict = {}
    for params in parser.items("DEFAULT"):
        params_dict[params[0]] = params[1]
    return params_dict


def print_status(status_dict):
    for key, value in status_dict.items():
        print(f"    {key}:  {' '.join(list(set(value)))}")
    print("\n")


def get_all_python_files():
    exclude_dirs = [".tox", "venv", ".pytest_cache", "site-packages", ".git"]
    for root, _, files in os.walk(os.path.abspath(os.curdir)):
        if [_dir for _dir in exclude_dirs if _dir in root]:
            continue

        for filename in files:
            file_path = os.path.join(root, filename)
            if filename.endswith(".py") and file_path != os.path.abspath(__file__):
                yield file_path
