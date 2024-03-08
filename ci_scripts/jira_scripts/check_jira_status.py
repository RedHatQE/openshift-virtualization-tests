import re

from jira import JIRA, JIRAError

from ci_scripts.utils import all_python_files, get_connection_params, print_status


# Needs to be update based on the branch.
EXPECTED_TARGET_VERSIONS = ["vfuture", "4.16", "4.15.1"]


def get_jira_connection():
    connection_params = get_connection_params()
    jira_connection = JIRA(
        token_auth=connection_params.get("token"),
        options={"server": connection_params.get("url")},
    )
    return jira_connection


def get_jira_metadata(jira_id, jira_connection):
    retries = 0
    max_retry = 3
    while True:
        try:
            return jira_connection.issue(
                id=jira_id, fields="status, issuetype, fixVersions"
            ).fields
        except JIRAError as e:
            # Check for inactivity error (adjust based on your library)
            if "Unauthorized" in str(e) or "Session timed out" in str(e):
                retries += 1
                print(
                    "Failed to get issue due to inactivity, retrying (%d/%d)",
                    retries,
                    max_retry,
                )
                if retries < max_retry:
                    jira_connection = get_jira_connection()  # Attempt reconnection
                else:
                    raise  # Re-raise the error after exceeding retries
            else:
                raise


def get_jira_fix_version(jira_metadata):
    fix_version = (
        re.search(r"([\d.]+)", jira_metadata.fixVersions[0].name)
        if jira_metadata.fixVersions
        else None
    )
    return fix_version.group(1) if fix_version else "vfuture"


def get_all_jiras_from_file(file_content):
    """
    Try to find all jira tickets in the file.
    Looking for the following patterns:
    - jira_id=CNV-12345  # call in is_jira_open
    - jira_id = CNV-12345  # when jira is constant
    - https://issues.redhat.com/browse/CNV-12345  # when jira is in a link in comments
    - pytest.mark.jira(CNV-12345)  # when jira is in a marker

    Args:
        file_content (str): The content of the file.

    Returns:
        list: A list of jira tickets.
    """
    issue_pattern = r"([A-Z]+-[0-9]+)"
    _pytest_jira_marker_bugs = re.findall(
        rf"pytest.mark.jira.*?{issue_pattern}.*", file_content, re.DOTALL
    )
    _is_jira_open = re.findall(rf"jira_id\s*=[\s*\"\']*{issue_pattern}.*", file_content)
    _jira_url_jiras = re.findall(
        rf"https://issues.redhat.com/browse/{issue_pattern}.*",
        file_content,
    )
    _is_jira_comments = re.findall(
        r"({issue_pattern}(?! <skip-jira-check>))", file_content, re.IGNORECASE
    )
    return set(
        _pytest_jira_marker_bugs + _is_jira_open + _jira_url_jiras + _is_jira_comments
    )


def get_jiras_from_python_files():
    jira_found = {}
    for filename in all_python_files():
        filename_for_key = re.findall(r"openshift-virtualization-tests/.*", filename)[0]
        with open(filename) as fd:
            if unique_jiras := get_all_jiras_from_file(file_content=fd.read()):
                jira_found[filename_for_key] = unique_jiras
    return jira_found


def main():
    closed_statuses = get_connection_params().get("resolved_statuses")
    closed_jiras = {}
    mismatch_bugs_version = {}
    jira_ids_with_errors = {}
    jira_ids_dict = get_jiras_from_python_files()
    jira_connection = get_jira_connection()
    for filename in jira_ids_dict:
        for jira_id in jira_ids_dict[filename]:
            try:
                jira_metadata = get_jira_metadata(
                    jira_id=jira_id, jira_connection=jira_connection
                )
                current_jira_status = jira_metadata.status.name.lower()
                if current_jira_status in closed_statuses:
                    closed_jiras.setdefault(filename, []).append(
                        f"{jira_id} [{current_jira_status}]"
                    )
                jira_target_release_version = get_jira_fix_version(
                    jira_metadata=jira_metadata
                )
                if not jira_target_release_version.startswith(
                    tuple(EXPECTED_TARGET_VERSIONS)
                ):
                    mismatch_bugs_version.setdefault(filename, []).append(
                        f"{jira_id} [{jira_target_release_version}]"
                    )
            except JIRAError as exp:
                jira_ids_with_errors.setdefault(filename, []).append(
                    f"{jira_id} [{exp.text}]"
                )
                continue

    if closed_jiras:
        print(f"{len(closed_jiras)} Jira tickets are closed and need to be removed:")
        print_status(status_dict=closed_jiras)

    if mismatch_bugs_version:
        print(
            f"{len(mismatch_bugs_version)} Jira bugs are not matched to the current branch's expected version list:"
            f" '{EXPECTED_TARGET_VERSIONS}' and need to be removed:"
        )
        print_status(status_dict=mismatch_bugs_version)

    if jira_ids_with_errors:
        print(f"{len(jira_ids_with_errors)} Jira ids had errors:")
        print_status(status_dict=jira_ids_with_errors)

    if closed_jiras or mismatch_bugs_version or jira_ids_with_errors:
        exit(1)


if __name__ == "__main__":
    main()
