import logging

from pylero.exceptions import PyleroLibException

from ci_scripts.polarion.polarion_utils import (
    PROJECT,
    get_polarion_ids_from_diff,
    git_diff_added_removed_lines,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
AUTOMATED = "automated"
NOT_AUTOMATED = "notautomated"
APPROVED = "approved"


def approve_tc(tc):
    tc.status = APPROVED
    tc.update()
    LOGGER.info(f"{tc.work_item_id} {APPROVED}")


def automate_and_approve_tc():
    git_diff = git_diff_added_removed_lines()
    added_ids, removed_ids = get_polarion_ids_from_diff(diff=git_diff)
    if added_ids or removed_ids:
        from pylero.work_item import TestCase

    for _id in removed_ids:
        if _id in added_ids:
            continue

        tc = TestCase(project_id=PROJECT, work_item_id=_id)
        if tc.caseautomation == AUTOMATED:
            LOGGER.info(f"{_id}: Mark as {AUTOMATED}, Setting '{NOT_AUTOMATED}'")
            tc.caseautomation = NOT_AUTOMATED
            approve_tc(tc=tc)

    for _id in added_ids:
        try:
            tc = TestCase(project_id=PROJECT, work_item_id=_id)
            if tc.caseautomation != AUTOMATED:
                LOGGER.info(f"{_id}: Not mark as {AUTOMATED}, Setting '{AUTOMATED}'")
                tc.caseautomation = AUTOMATED
                approve_tc(tc=tc)

            if tc.caseautomation == AUTOMATED and tc.status != APPROVED:
                LOGGER.info(f"{_id} already {AUTOMATED}")
                approve_tc(tc=tc)

        except PyleroLibException as ex:
            LOGGER.warning(f"{_id}: {ex}")


if __name__ == "__main__":
    automate_and_approve_tc()
