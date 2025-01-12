import logging
import sys

from pylero.exceptions import PyleroLibException

from ci_scripts.polarion.polarion_utils import (
    PROJECT,
    get_polarion_ids_from_diff,
    git_diff_added_removed_lines,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def has_verify():
    git_diff = git_diff_added_removed_lines()
    added_ids, _ = get_polarion_ids_from_diff(diff=git_diff)
    missing = []
    if added_ids:
        from pylero.work_item import Requirement, TestCase

        for _id in added_ids:
            has_req = False
            LOGGER.info(f"Checking if {_id} verifies any requirement")
            tc = TestCase(project_id=PROJECT, work_item_id=_id)
            for link in tc.linked_work_items:
                try:
                    Requirement(project_id=PROJECT, work_item_id=link.work_item_id)
                    has_req = True
                    break
                except PyleroLibException:
                    continue

            if not has_req:
                LOGGER.error(f"{_id}: Is missing requirement")
                missing.append(_id)

        if missing:
            missing_str = "\n".join(missing)
            LOGGER.error(f"Cases with missing requirement: {missing_str}")
            sys.exit(1)


if __name__ == "__main__":
    has_verify()
