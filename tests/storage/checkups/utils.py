import logging
import re

from tests.storage.checkups.constants import ACCESS_MODES

STATUS = "status"
STATUS_FAILURE_REASON = f"{STATUS}.failureReason"
STATUS_SUCCEEDED = f"{STATUS}.succeeded"
STATUS_RESULT_STR = f"{STATUS}.result"

LOGGER = logging.getLogger(__name__)


def assert_results_in_configmap(configmap, expected_failure_msg=None, expected_result=None, result_entry=None):
    configmap_results = configmap.instance.data
    expected_checkup_result = "false" if expected_failure_msg else "true"

    # basic conditions for success/failure
    assert re.search(expected_checkup_result, configmap_results[STATUS_SUCCEEDED])
    if expected_failure_msg:
        assert re.search(expected_failure_msg, configmap_results[STATUS_FAILURE_REASON])
    else:
        assert configmap_results[STATUS_FAILURE_REASON] == ""

    # specific status result check
    if expected_result:
        assert re.search(
            expected_result,
            configmap_results.get(f"{STATUS_RESULT_STR}.{result_entry}"),
        )


def update_storage_profile(storage_profile):
    claim_property_set_dict = storage_profile.instance.status.claimPropertySets[0]
    claim_property_set_dict[ACCESS_MODES].append(claim_property_set_dict[ACCESS_MODES][0])
    return claim_property_set_dict
