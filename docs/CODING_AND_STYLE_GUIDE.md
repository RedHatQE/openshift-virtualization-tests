## General

- Remember [The Zen of Python](https://www.python.org/dev/peps/pep-0020/)
- The repository styleguide is based on the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
- The repository uses [pre-commit](https://pre-commit.com/) to enforce the styleguide.

## Documentation
- Use [Google-format](https://google.github.io/styleguide/pyguide.html#381-docstrings) for docstrings.
- Add docstrings to document functions, classes, and modules.
- Avoid inline comments; Write self-explanatory code that can be easily understood.
Only add comments when necessary. For example, when using complex regex.

## Typing
- Add typing to new code; typing is enforced using [mypy](https://mypy-lang.org/)
- Rules are defined in [pyproject.toml](../pyproject.toml#L10)
- For more information, see [typing](https://docs.python.org/3/library/typing.html)

# Coding standards
- Reduce duplicate code, before writing new function search for it, probably someone already wrote it or one that should serve your needs.
  - The project uses external packages that may already have a functionality that does what you need.
    To see the available packages, see the [pyproject.toml](../pyproject.toml) file.
- Variables:
  - When using a variable more than once, save it and reuse.
  - Use descriptive names for tests, variables, functions, classes, etc.
  - Meaningful names are better than short names.
  - Do not use single-letter names.
- When applicable, to reduce load and unnecessary calls, use [caching](https://docs.python.org/3/library/functools.html#functools.cache).
- avoid saving object attributes to variables, but rather use them directly.
  - Example:
  ```python
  # Bad
  myattribute = foo.myattribute
  my_func(arg1=myattribute)

  # Good
  my_func(arg1=foo.myattribute)
  ```
- Keep functions and fixtures close to where they're used, if needed to move them later for more modules to use them.  See [Directory structure](#directory-structure) for more information.
- Call functions using argument names to make it clear what is being passed and easier refactoring.
- Imports: Always use absolute paths
- Imports: when possible, avoid importing a module but rather import specific functions.  This should not come at the expense of readability and context.
  If needed, import the module and use the module name to call the function.
- Do not import from `conftest.py` files. These files must contain fixtures only and not utility functions, constants, etc.
- Scopes and encapsulation:
  - Use closures and nested functions only when it solves a problem that has no other elegant solution.
  - Avoid using nested functions to implement encapsulation and scope "protection."
  - When there is a need to preserve the state, have encapsulation or scope protection, use classes.
- Code extensibility should not come at the expense of readability; remember that someone else will need to look/use/maintain the code.
  - Avoid complex solutions when there is no explicit-foreseen use case ahead.
  - Keep focus on current requirements; do not prepare code for the future just because it may be useful.
  - Reason well for code structure when it is not obvious
- Every function, variable, fixture, etc. written in the code - must be used, or else removed.
- Log enough to make you debug and understand the flow easy, but do not spam the log with unhelpful info.
    Error logs should be detailed with what failed, status and so on.

## Directory structure
- Each feature should have its own subdirectory under the relevant component's subdirectory. Directories should be named according to the feature.
- To improved readability, easier navigation, and maintenance:
  - Feature tests can be split into multiple files.
  - Feature tests can be split into multiple subdirectories.
- Tests are to be placed in `test_<functionality>.py` file; this is where the actual tests are written.
  `<functionality_name>` describes the functionality tested in this test file.
- If helper utils are needed, they should be placed in the test's subdirectory.
- If specific fixtures are needed, they should be placed in a `conftest.py` file under the test's subdirectory.

## conftest
- Top level [conftest.py](../conftest.py) contains pytest native fixtures.
- General tests [conftest.py](../tests/conftest.py) contains fixtures that are used in multiple tests by multiple teams.
- If needed, create new `conftest.py` files in the relevant directories.


## Fixtures
- Ordering: Always call pytest native fixtures first, then session-scoped fixtures and then any other fixtures.
- Fixtures should handle setup (and the teardown, if needed) needed for the test(s), including the creation of resources, for example.
- Fixtures which call other fixtures but without using their return value should be called using `@pytest.mark.usefixtures(<fixture name>)`
- Fixtures should do one action/functionality only.
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

- Pytest reports failures in fixtures as `ERROR`
- A fixture name should be a noun that describes what the fixture provides (i.e., returns or yields), rather than a verb.
For example:
  - If a test needs a storage secret, the fixture should be called 'storage_secret' and not 'create_secret'.
  - If a test needs a directory to store user data, the fixture should be called 'user_data_dir' and not 'create_directory'.
- If there's more than one fixture with the same functionality, but with a different scope, add `_scope_<scope>` as a suffix to the fixture name.`
- Note fixture scope, test execution times can be reduced by selecting the right scope.
Pytest default fixture invocation is "function", meaning the code in the fixture will be executed every time the fixture is called.
Broader scopes (class, module etc) will invoke the code only once within the given scope and all tests within the scope will use the same instance.
- Use request.param to pass parameters from test/s to fixtures; use a dict structure for readability.  For example:

```code
@pytest.mark.parametrize(
  "my_secret",
    [
      pytest.param({"name": "my-secret", "data-dict": {"key": "value"}}}),
    ]
  )
def test_secret(my_secret):
    pass

@pytest.fixture()
def my_secret(request):
  secret = Secret(name=request.param["name"], data_dict=request.param["data-dict"])
```


## Tests
- Pytest reports tes failures as `FAILED`.
- Each test should have a clear purpose and should be easy to understand.
- Each test should verify a single aspect of the product.
- Preferably, each test should be independent of other tests.
- When there's a dependency between tests use pytest dependency plugin to mark the relevant hierarchy between tests (https://github.com/RKrahl/pytest-dependency)
- When adding a new test, apply relevant marker(s) which may apply.
  Check [pytest.ini](../pytest.ini) for available markers; additional markers can always be added when needed.
- Classes are good to group related tests together, for example, when they share a fixture.
  You should NOT group unrelated tests in one class (because it is misleading the reader).
