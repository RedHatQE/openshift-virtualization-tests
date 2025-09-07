import re

import pytest

from tests.observability.metrics.constants import GO_VERSION_STR, KUBE_VERSION_STR
from tests.observability.metrics.utils import assert_virtctl_version_equal_metric_output
from utilities.infra import run_virtctl_command


@pytest.fixture()
def virtctl_go_kube_server_version():
    virtctl_go_kube_version_dict = {}
    data = run_virtctl_command(command=["version"])[1]
    virtctl_go_kube_version_dict[GO_VERSION_STR] = re.findall(
        r'(?:Server).*GoVersion:"(.*)",\s+Compiler',
        data,
    )[0]
    virtctl_go_kube_version_dict[KUBE_VERSION_STR] = re.findall(
        r'(?:Server).*version.*{GitVersion:"(.*)",\s+GitCommit',
        data,
    )[0]
    return virtctl_go_kube_version_dict


@pytest.mark.polarion("CNV-11017")
@pytest.mark.s390x
def test_kubevirt_info_version(prometheus, virtctl_go_kube_server_version):
    metric_result_output = prometheus.query_sampler(query="kubevirt_info")
    assert_virtctl_version_equal_metric_output(
        virtctl_server_version=virtctl_go_kube_server_version,
        metric_output=metric_result_output,
    )
