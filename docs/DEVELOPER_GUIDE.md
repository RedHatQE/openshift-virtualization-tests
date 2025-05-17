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
  - Make sure you follow the [Style guide](STYLE_GUIDE.md)
  - Make sure you have [pre-commit](https://pre-commit.com/) package installed
  - Make sure you have [tox](https://tox.readthedocs.io/en/latest/) package installed
- PRs that are not ready for review (but needed to be pushed for any reason) should have [WIP] in the title and labeled as "wip".
  - When a PR is ready for review, remove the [WIP] from the title and remove the "wip" label.
- PRs should be relatively small; if needed, the PRs should be split and depend on each other.
  - Small PRs will get quicker review.
  - Small PRs comments will be fixed quicker and merged quicker.
  - Both the reviewer and the committer will benefit from this.
- When a refactor is needed as part of the current PR, the refactor should be done in another PR and the current PR should be rebased on it.
- Please address each comment in code review
  - If a comment was addressed and accepted, please comment as done and resolve.
  - If a comment was addressed and rejected or additional discussion is needed, add your input and do not resolve the comment.
  - To minimize the number of comments, please try to address all comments in one PR.
- Before a PR can be merged:
  - PRs must be verified and marked with "verified" label.
  - PRs must be reviewed by at least two reviewers other than the committer.
  - All CI checks must pass.

## Branching strategy
The project follows Red Hat Openshift Virtualization versions lifecycle.
If needed, once your PR is merged to `main`, cherry-pick your PR to the relevant branch(es).


## Python
- Reduce duplicate code, before writing new function search for it, probably someone already wrote it or one that should serve your needs.
  - The project uses external packages that may already have a functionality that does what you need.
- When using a variable more than once, save it and reuse.
- Keep functions and fixtures close to where they're used, if needed to move them later for more modules to use them.
- Call functions using argument names to make it clear what is being passed and easier refactoring.
- Imports: Always use absolute paths
- Imports: when possible, avoid importing a module but rather import specific functions
- Do not import from `conftest.py` files. These files must contain fixtures only and not utility functions, constants etc.
- Avoid using nested functions.
- Flexible code is good, but:
  - Should not come at the expense of readability; remember that someone else will need to look/use/maintain the code.
  - Do not prepare code for the future just because it may be useful.
  - Every function, variable, fixture, etc. written in the code - must be used, or else removed.
- Log enough to make you debug and understand the flow easy, but do not spam the log with unuseful info.
Error logs should be detailed with what failed, status and so on.

## Directory structure
- Each feature should have its own subdirectory under the relevant component's subdirectory.
- If needed, split feature tests into multiple files.
- If needed, split into multiple subdirectories.
- Each test should have its own file where the actual tests are written.
- If helper utils are needed, they should be placed in the test's subdirectory.
- If specific fixtures are needed, they should be placed in a `conftest.py` file under the test's subdirectory.


## Interacting with Kubernetes/OpenShift APIs
The project utilizes [openshift-python-wrapper](https://github.com/RedHatQE/openshift-python-wrapper).
Please refer to the [documentation](https://github.com/RedHatQE/openshift-python-wrapper/blob/main/README.md)
and the [examples](https://github.com/RedHatQE/openshift-python-wrapper/tree/main/examples) for more information.


## conftest
- Top level [conftest.py](../conftest.py) contains pytest native fixtures.
- General tests [conftest.py](../tests/conftest.py) contains fixtures that are used in multiple tests by multiple teams.
- If needed, create new `conftest.py` files in the relevant directories.


## Fixtures
- Ordering: Always call pytest native fixtures first, then session-scoped fixtures and then any other fixtures.
- Fixtures should handle setup (and the teardown, if needed) needed for the test(s), including the creation of resources, for example.
- Fixtures should do one thing only.
For example, instead of:

```python
@pytest.fixture()
def network_vm():
    with NetworkAttachmentDefinition(name=...) as nad:
      with VirtualMachine(name=..) as vm:
        yield vm
```

Do:

```python
@pytest.fixture()
def network_attachment_definition():
    with NetworkAttachmentDefinition(name=...) as nad:
      yield nad

@pytest.fixture(network_attachment_definition)
def model_inference_service(network_attachment_definition):
    with VirtualMachine(name=..) as vm:
        yield vm

```

- Pytest reports failures in fixtures as ERROR
- A fixture name should be a noun that describes what the fixture provides (i.e. returns or yields), rather than a verb.
For example:
  - If a test needs a storage secret, the fixture should be called 'storage_secret' and not 'create_secret'.
  - If a test needs a directory to store user data, the fixture should be called 'user_data_dir' and not 'create_directory'.
- Note fixture scope, test execution times can be reduced by selecting the right scope.
Pytest default fixture invocation is "function", meaning the code in the fixture will be executed every time the fixture is called.
Broader scopes (class, module etc) will invoke the code only once within the given scope and all tests within the scope will use the same instance.
- Use request.param to pass parameters from test/s to fixtures; use a dict structure for readability.  For example:

```code
@pytest.mark.parametrize(
"my_secret",
[
pytest.param(
{"name": "my-secret", "data-dict": {"key": "value"}}},
),

def test_secret(my_secret):

    pass

@pytest.fixture()
def my_secret(request):
secret = Secret(name=request.param["name"], data_dict=request.param["data-dict"])
```


## Tests
- Pytest reports failures in fixtures as FAILED
- Each test should have a clear purpose and should be easy to understand.
- Each test should verify a single aspect of the product.
- Preferably, each test should be independent of other tests.
- When there's a dependency between tests use pytest dependency plugin to mark the relevant hierarchy between tests (https://github.com/RKrahl/pytest-dependency)
- When adding a new test, apply relevant marker(s) which may apply.
Check [pytest.ini](../pytest.ini) for available markers; additional markers can always be added when needed.
- Classes are good to group related tests together, for example, when they share a fixture.
You should NOT group unrelated tests in one class (because it is misleading the reader).


# Development


## Fork openshift-virtualization-tests repo

Open https://github.com/RedHatQE/openshift-virtualization-tests and fork it to your GitHub account.

## Clone your forked repo
```bash
git clone https://github.com/<your-github-username>/openshift-virtualization-tests.git
```

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
pre-commit install --hook-type commit-msg
```

## Check the code
### pre-commit

When submitting a pull request, make sure to fill all the required, relevant fields for your PR.
Make sure the title is descriptive and short.
Checks tools are used to check the code are defined in .pre-commit-config.yaml file
To install pre-commit:

```bash
pre-commit install -t pre-commit -t commit-msg
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

Comment your GitHub PR:

```bash
/build-and-push-container
```

You can add additional arguments when creating the container. Supported arguments can be found in the Dockerfile
and Makefile of the openshift-virtualization-tests repository.

For example, this command will create a container with the openshift-virtualization-tests PR it was run against and the latest commit of
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
This same field can be used to test a specific container created from a openshift-virtualization-tests PR.

To pass parameters to pytest command add them to `PYTEST_PARAMS`.
for example `-k 'network'` will run only tests that match 'network'
