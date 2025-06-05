# Project Structure

openshift-virtualization-tests is a public repository under the [RedHatQE organization](https://github.com/RedHatQE) on GitHub.

The project is structured as follows:
- [tests](../tests): Base directory for pytest tests
  - Each component has its own directory
  - Each feature has its own directory
- [utilities](../utilities): Base directory for utility functions
  - Each module contains a set of utility functions related to a specific topic, for example:
    - [infra](../utilities/infra.py): Infrastructure-related (cluster resources) utility functions
    - [constants](../utilities/constants.py): Constants used in the project
- [docs](../docs): Documentation
- [py_config](../tests/global_config.py) contains tests-specific configuration which can be controlled from the command line.
Please refer to [pytest-testconfig](https://github.com/wojole/pytest-testconfig) for more information.


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
  - Make sure you have [pre-commit](https://pre-commit.com/) package installed
  - Make sure you have [tox](https://tox.readthedocs.io/en/latest/) package installed

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

We use checks tools that are defined in .pre-commit-config.yaml file
To install pre-commit:

```bash
pip install pre-commit --user
pre-commit install
```

Run pre-commit:

```bash
pre-commit run --all-files
```

pre-commit will try to fix the errors.
If some errors where fixed, git add & git commit is needed again.
commit-msg uses gitlint (<https://jorisroovers.com/gitlint/>)


### tox
CI uses [tox](https://tox.readthedocs.io/en/latest/) and will run the code under tox.ini
To check for issues locally run:

```bash
tox
```

### Commit message

It is essential to have a good commit message if you want your change to be reviewed.

- Write a short one-line summary
- Use the present tense (fix instead of fixed)
- Use the past tense when describing the status before this commit
- Add a link to the related jira card (required for any significant automation work)
  - `jira-ticket: https://issues.redhat.com/browse/<jira_id>`
  - The card will be automatically closed once PR is merged

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
