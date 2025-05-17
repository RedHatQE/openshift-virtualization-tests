## General

- Remember [The Zen of Python](https://www.python.org/dev/peps/pep-0020/)
- The repository styleguide is based on the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
- The repository uses [pre-commit](https://pre-commit.com/) to enforce the styleguide.

## Naming
- Use descriptive names for tests, variables, functions, classes, etc.
- Meaningful names are better than short names.
- Do not use single-letter names.

## Documentation
- Use [Google-format](https://google.github.io/styleguide/pyguide.html#381-docstrings) for docstrings.
- Add docstrings to document functions, classes, and modules.
- Avoid inline comments; Write self-explanatory code that can be easily understood.
Only add comments when necessary. For example, when using complex regex.

## Typing
- Add typing to new code; typing is enforced using [mypy](https://mypy-lang.org/)
- Rules are defined in [our pyproject.toml file](//pyproject.toml#L10)
- For more information, see [typing](https://docs.python.org/3/library/typing.html)
