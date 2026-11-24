# Project Structure

openshift-virtualization-tests is a public repository under the [RedHatQE organization](https://github.com/RedHatQE) on GitHub.

The project is structured as follows:
- [tests](../tests): Base directory for pytest tests
  - Each component has its own directory
  - Each feature has its own directory
- [utilities](../utilities): Base directory for utility functions
  - Each module contains a set of utility functions related to a specific topic, for example:
    - [infra](../utilities/infra.py): Infrastructure-related (cluster resources) utility functions
    - [constants](../utilities/constants/): Shared constants package — see [Code Organization](CODE_ORGANIZATION.md#constants-utilitiesconstants)
  - [tests/fixtures](../tests/fixtures/): Shared pytest fixture implementations — see [Code Organization](CODE_ORGANIZATION.md#fixtures-testsfixtures-and-conftestpy)
  - [unittests](../utilities/unittests): Mocked unit tests for utility modules, run with `uv run tox -e utilities-unittests`
- [libs](../libs): Shared domain libraries (`infra`, `net`, `storage`, `vm`)
- [scripts](../scripts): Standalone internal tooling and automation scripts (several include their own `tests/` suites)
- [docs](../docs): Documentation — including [Code Organization](CODE_ORGANIZATION.md) for constants, utilities, and fixtures
- [py_config](../tests/global_config.py) contains tests-specific configuration which can be controlled from the command line.
Please refer to [pytest-testconfig](https://github.com/wojole/pytest-testconfig) for more information.

This layout is also the map used to trace which tests a package update can affect — see [Verifying dependency bumps](#verifying-dependency-bumps).


# Contribution
To contribute code to the project:

## Pull requests
- Fork the project and work on your forked repository
- Before submitting a new pull request:
  - Make sure you follow the [Coding and Style Guide](CODING_AND_STYLE_GUIDE.md)
  - Check the [prerequisites](#prerequisites) section under the [Development](#development) section
- PRs that are not ready for review (but needed to be pushed for any reason) should be set as `Draft` in GitHub.
  - When a PR is ready for review, mark it as ready for review.
- PRs should be relatively small; if needed, the PRs should be split and depend on each other.
  - Small PRs will get quicker review.
  - Small PRs comments will be fixed quicker and merged quicker.
  - Both the reviewer and the committer will benefit from this.
- When a refactor is needed as part of the current PR, the refactor should be done in another PR and the current PR should be rebased on it.
- Please address each comment in code review
  - If a comment is addressed and accepted:
      - The author should comment “done” and add 👍 if they agree with the resolution.
      - The author can then mark that comment as `resolved`.
  - If a comment was addressed and rejected or additional discussion is needed, add your input and do not resolve the comment.
  - To minimize the number of comments, please try to address all comments in one PR.
- The repository is using [CodeRabbit](https://www.coderabbit.ai/) for PR reviews; all comments must be addressed in the PR.
- Before a PR can be merged:
  - PRs must be verified and marked with "verified" label.
    - PRs must be reviewed and approved (by adding `/lgtm` comment or using GitHubs' approve) by at least two reviewers other than the committer.
      For the PR to be merged, the accepted reviewers are the ones that appear in the modified code's `OWNERS` file or root approvers.
    - PRs must be approved (by adding `/approve` comment) by at least one of the approvers in the root `OWNERS` file.
      If the `OWNERS` file relevant to the modified code contains `root-approvers: False`, the approvers in the root `OWNERS` file are not required to approve the PR.
  - All CI checks must pass.
    - If `can-be-merged` check is marked as failed, check the job to see the reason(s).

## Branching strategy
The project follows Red Hat Openshift Virtualization versions lifecycle.
If needed, once your PR is merged to `main`, cherry-pick your PR to the relevant branch(es).


# Development


## Prerequisites
  - Install [uv](https://docs.astral.sh/uv/)
  - Python 3.14 or a supported `uv` Python installation
  - Install the command-line tools used below as uv-managed tools:

```bash
uv tool install pre-commit
uv tool install tox
uv tool update-shell
```

Restart your shell, or source the startup file updated by `uv tool update-shell` (for example, `source ~/.bashrc`), so the tool executables are available in `PATH` to `uv run`.
The commands below intentionally invoke both tools through `uv run`.

## Coding standards and style guide
- Refer to the [coding_and_style guide](CODING_AND_STYLE_GUIDE.md) for style guide rules.

## Interacting with Kubernetes/OpenShift APIs
The project utilizes [openshift-python-wrapper](https://github.com/RedHatQE/openshift-python-wrapper).
Please refer to the [documentation](https://github.com/RedHatQE/openshift-python-wrapper/blob/main/README.md)
and the [examples](https://github.com/RedHatQE/openshift-python-wrapper/tree/main/examples) for more information.

## How to verify your patch

Determining the depth of verification steps for each patch is left for the
author and their reviewer. It's required that the procedure used to verify a
patch is listed in comments to the review request.

### Check the code

We use the checks defined in `.pre-commit-config.yaml`. Install the Git hooks with:

```bash
uv run pre-commit install
```

Run all pre-commit checks with:

```bash
uv run pre-commit run --all-files
```

The configuration includes autoflake, Ruff, Flake8, mypy, gitleaks, TOML validation,
large-file detection, and the project policy hooks: the stateless
`check-banned-paths`/`check-banned-constructs` whole-file hooks and the staged-diff
`check_policy.py` families (staged paths, forbidden pytest skips, mechanical Python
rules, explicit resource clients, reviewed linter-directive exceptions, new
product-test STD structure, and STP link verification).

`AGENTS.md` is authoritative for contribution policy. See the
[`scripts/pre_commit_hooks/README.md`](../scripts/pre_commit_hooks/README.md) for the
hooks' exact scope, staged/index ratchet behavior, and the CI enforcement tiers
(pre-commit.ci for the stateless hooks, the Pre-commit Policy Checks GitHub Actions
workflow for the staged-diff tier). In particular, even `uv run pre-commit run --all-files` checks the staged/index policy snapshot rather
than auditing every historical worktree violation.

Some hooks automatically fix files. If a hook changes a file, stage the fix and run the
checks again. Commit messages are checked by gitlint (<https://jorisroovers.com/gitlint/>).


### tox
CI uses [tox](https://tox.readthedocs.io/en/latest/) and will run the code under tox.ini
To check for issues locally run:

```bash
uv run tox
```

### Commit message

It is essential to have a good commit message if you want your change to be reviewed.

- Write a short one-line summary
- Use the present tense (fix instead of fixed)
- Use the past tense when describing the status before this commit
- Add a link to the related jira card (required for any significant automation work)
  - `jira-ticket: https://issues.redhat.com/browse/<jira_id>`
  - The card will be automatically closed once PR is merged

### Request a test execution plan

Comment on your GitHub PR:

```bash
/test-plan
```

This triggers CodeRabbit to analyze the PR's changed files and post an inline review comment with a test execution plan (smoke/gating impact, affected tests to run).

### CodeRabbit post-merge learnings

After a pull request merges into the default branch, CodeRabbit can open a follow-up pull request that documents new CodeRabbit "Learnings added" guidance into [`AGENTS.md`](../AGENTS.md). Only the `Learning:` text is documented (not learning metadata). General / repository-wide rules go in the root `AGENTS.md`. Learnings that are specifically about a directory or area go in a nested `AGENTS.md` in that area (created if needed); `File:` is used as a hint for which directory when present. The action does not update `.coderabbit.yaml` for learnings.

**Trigger**

- Configured in `.coderabbit.yaml` under `reviews.post_merge_actions` as `CodeRabbit learnings from merged PR`.
- Runs only when that action's checkbox is still checked in the CodeRabbit walkthrough at merge time.

**Where it looks for learnings**

CodeRabbit-authored comments that contain a "Learnings added" marker (a Markdown heading, or an HTML `<summary>…Learnings added…</summary>` details block), in any of:

- top-level conversation comments
- inline review comments (Files changed), including replies in those threads
- pull request review bodies

**Acknowledgment (when a learning is skipped)**

- Inline review threads: skip the learning only if a human (not a bot) posted a direct reply **after** that "Learnings added" comment in the **same** review thread.
- Top-level conversation comments and review bodies: a later unrelated human comment in the PR conversation does **not** count as acknowledgment; those learnings are still documented.

**When it does nothing (no-op)**

No follow-up pull request is opened when there are no qualifying "Learnings added" markers, every remaining learning is already documented in the applicable root or nested `AGENTS.md`, or all remaining inline learnings were acknowledged in the same thread. The post-merge result comment reports that no update was needed.

If comments cannot be read at all, the post-merge result reports an incomplete scan.

**Follow-up pull request**

When there is work to do, CodeRabbit opens one follow-up pull request against the default branch with the documented rules. The follow-up title and description are set by the CodeRabbit platform (not fully customizable via the action prompt). To find which merged pull request triggered a follow-up:

- On the **source** merged pull request, open the 🚀 Post-Merge Actions result comment (it links to the follow-up).
- On the **follow-up** pull request, check the timeline for a cross-reference to the source pull request.

**Failure**

If creating the follow-up pull request fails, CodeRabbit reports the failure in the post-merge result comment on the merged pull request.

### Re-run smoke tests

Comment on your GitHub PR (OWNER / MEMBER / COLLABORATOR only):

```bash
/rerun-smoke
```

This adds the `retest-smoke` label so Jenkins job `github-events-listener` can pick up a smoke re-run (Jenkins typically removes the label after processing).
If `retest-smoke` is already on the PR and was added less than 4 hours ago, the workflow skips re-adding the label and logs guidance to check that Jenkins job.
If the label is still present and older than 4 hours, the workflow removes and re-adds it so Jenkins sees a fresh labeled event.
A thumbs-up on the comment means the workflow accepted the request and added or refreshed the label.
If the request is skipped (4-hour cooldown, or label present without usable label history), the thumbs-up is replaced with 👎 — check the workflow Action logs and Jenkins job `github-events-listener`.

### Verifying dependency bumps

Use this procedure for any dependency or lockfile bump.
To update packages and regenerate `uv.lock`, see [Getting started](GETTING_STARTED.md#installation).

#### Baseline checks (no cluster required)

Run these first on every bump:

```bash
# Manifest and lockfile consistency, and a clean installation from the lockfile
uv lock --check
uv sync --locked
```

Then stage `pyproject.toml`, `uv.lock`, and any other modified files (for example
`git add pyproject.toml uv.lock`) and run the linters, type checks, and policy hooks as described
in [Check the code](#check-the-code). The staged-diff policy hooks always inspect the staged Git
index rather than the unstaged worktree, even with `--all-files`, so unstaged changes are skipped
by those checks.

Run the full suite as described in [tox](#tox). It covers pytest collection on `amd64`,
`arm64`, `s390x`, and `multiarch`; upgrade modes (`--upgrade` for CNV, OCP, and EUS;
`--upgrade_custom` for CNV and OCP); `tests/global_config_rh_it.py`; `-m smoke
--collect-only`; `--setup-plan`; every top-level `tests/` directory; `unused-code`; and
`utilities-unittests`.

If the bumped package is used by tooling under `scripts/`, run that tool's unit tests.
These suites have their own `pytest.ini`/`conftest.py`, so isolate them from the root
test configuration:

```bash
# Tool with a local pytest.ini
uv run pytest -c scripts/<tool>/tests/pytest.ini --confcutdir=scripts/<tool>/tests scripts/<tool>/tests

# Tool without a local pytest.ini
uv run pytest -o addopts="" --confcutdir=scripts/<tool>/tests scripts/<tool>/tests
```

Finally verify container packaging:

- Locally: `make build-container` (see [CONTAINERIZE_TESTS.md](CONTAINERIZE_TESTS.md)).
- On a PR: `/build-and-push-container` (see
  [Build and push a container with your changes](#build-and-push-a-container-with-your-changes)).

#### Trace impact using the project structure

This section relies on the layout described in [Project Structure](#project-structure).

- Direct imports: `git grep -n "<module_name>" -- conftest.py tests utilities libs scripts`. The
  Python import module name can differ from the package name in `pyproject.toml` (for example
  `openshift-python-wrapper` → `ocp_resources`, `openshift-python-utilities` → `ocp_utilities`,
  `pyhelper-utils` → `pyhelper_utils`, `timeout-sampler` → `timeout_sampler`, `pyvmomi` →
  `pyVim`/`pyVmomi`).
- Transitive dependencies (for example `cryptography`, `pyjwt`, `dnspython`): use
  `uv tree --invert --package <package_name>` to find which direct dependency pulls it in,
  then trace that direct dependency's usage.
- On a PR, comment `/test-plan` (see [Request a test execution plan](#request-a-test-execution-plan))
  for automated impact tracing.

#### Select manual cluster tests by scope

**Core / cross-cutting dependencies** — used by `conftest.py`, shared `utilities/`, `libs/`,
cluster API/HTTP clients, or pytest itself (for example `openshift-python-wrapper`,
`openshift-python-utilities`, `kubernetes`, `pyhelper-utils`, `timeout-sampler`, `requests`,
`urllib3`, `pytest` and pytest plugins):

- Start with the smoke suite (`uv run pytest -m smoke`, or `/rerun-smoke` on the PR — see
  [Re-run smoke tests](#re-run-smoke-tests)), which exercises cluster API access, VM lifecycle,
  storage clone/upload, and core session fixtures.
- For high-impact bumps (for example `openshift-python-wrapper`, `kubernetes`, `pytest`), also
  run representative tests across the affected `tests/<component>/` directories, or `-m gating`
  via Jenkins.

**Domain-specific dependencies** — imported only by specific components or utility modules:

- `netaddr` in the networking utilities and `tests/network/`.
- `pyvmomi` in `tests/network/provider_migration/`.
- `pexpect` in console/VNC/libguestfs helpers.
- `sqlalchemy` in `utilities/database.py`, exercised by `conftest.py` with `--data-collector` and
  by `utilities/unittests/test_database.py`.
- `pytest-jira` with `--jira`.
- `jira` in `utilities/jira.py`, exercised by tests calling `is_jira_open()` and by
  `utilities/unittests/test_jira.py`.

Run the matching `tests/<component>/<feature>/` directory or test files directly against a
cluster, along with any matching unit tests under `utilities/unittests/` or
`scripts/<tool>/tests/`.

See [Running Tests](RUNNING_TESTS.md) for CLI filtering options (`-m`, `-k`, `--tc-file`).

### Run the tests via a Jenkins job

#### Build and push a container with your changes

Comment on your GitHub PR:

```bash
/build-and-push-container
```

You can add additional arguments when creating the container. Supported arguments can be found in the Dockerfile
and Makefile of the openshift-virtualization-tests repository.

For example, this command will create a container with the openshift-virtualization-tests PR it was run against and a specific commit of
a wrapper PR:

```bash
/build-and-push-container --build-arg OPENSHIFT_PYTHON_WRAPPER_COMMIT=<commit_hash>
```

Container created with the `/build-and-push-container` command is automatically pushed to quay and can be used by
Jenkins test jobs for verification (see `Run the Jenkins test jobs for openshift-virtualization-tests` section for more details).

#### Run the Jenkins test jobs for openshift-virtualization-tests

Open relevant test jobs in jenkins
Click on Build with Parameters.
Under `CLUSTER_NAME` enter your cluster's name.
Under `IMAGE_TAG` enter your image tag, example: openshift-virtualization-tests-github:pr-<pr_number>
This same field can be used to test a specific container created from an openshift-virtualization-tests PR.

To pass parameters to pytest command add them to `PYTEST_PARAMS`.
for example `-k 'network'` will run only tests that match 'network' keyword
