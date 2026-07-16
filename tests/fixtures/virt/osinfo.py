import os
import re

import pytest
import requests
from bs4 import BeautifulSoup
from pytest_testconfig import config as py_config

from tests.utils import download_and_extract_tar
from utilities.artifactory import get_artifactory_header


@pytest.fixture(scope="module")
def osinfo_repo():
    return f"{py_config['servers']['https_server']}/cnv-tests/osinfo-db/"


@pytest.fixture(scope="module")
def latest_osinfo_db_file_name(osinfo_repo):
    sorted_osinfo_repo = f"{osinfo_repo}/?C=M;O=A"
    soup_page = BeautifulSoup(
        markup=requests.get(sorted_osinfo_repo, headers=get_artifactory_header(), verify=False).text,
        features="html.parser",
    )
    full_link = soup_page.findAll(name="a", attrs={"href": re.compile(r"osinfo-db-[0-9]*.tar.xz")})

    assert full_link, "No osinfo-db file was found."

    return full_link[-1].get("href")


@pytest.fixture(scope="module")
def downloaded_latest_libosinfo_db(tmpdir_factory, latest_osinfo_db_file_name, osinfo_repo):
    """Obtain the osinfo path."""
    osinfo_path = tmpdir_factory.mktemp("osinfodb")
    download_and_extract_tar(
        tarfile_url=f"{osinfo_repo}{latest_osinfo_db_file_name}",
        dest_path=osinfo_path,
    )
    osinfo_db_file_name_no_suffix = latest_osinfo_db_file_name.partition(".")[0]
    yield os.path.join(osinfo_path, osinfo_db_file_name_no_suffix)
