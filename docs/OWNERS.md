Taken from [Kubernetes OWNERS guide](https://www.kubernetes.dev/docs/guide/owners/#owners)

# OWNERS files
Each directory that contains a unit of independent code or content may also contain an OWNERS file. This file applies to everything within the directory, including the OWNERS file itself, sibling files, and child directories.

OWNERS files are in YAML format and support the following keys:

- approvers: a list of GitHub usernames or aliases that can /approve a PR.
- reviewers: a list of GitHub usernames or aliases that are good candidates to /lgtm a PR.
- emeritus_approvers a list of GitHub usernames of folks who were previously in the approvers section, but are no longer actively approving code.
