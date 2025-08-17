# Generated using Claude cli

# CNV Utilities Testing Framework

## Overview

This directory contains unit tests for the Openshift Virtualization (former CNV) utilities framework.

The testing suite is designed to provide comprehensive coverage of utility modules while being completely independent of the main project's test infrastructure.

## Purpose

The utilities testing framework serves to:

- **Prevent regressions** when modifying utility code
- **Enable safe refactoring** with confidence in preserved functionality

## Testing Architecture

### Independent Test Suite
- Uses its own `pytest.ini` and `conftest.py` configuration
- Isolated from main project test dependencies
- Mocks external resources (Kubernetes, OpenShift, file system)
- Fast execution with no network or cluster dependencies

### Test Structure
```
utilities/unittests/
├── conftest.py          # Shared fixtures and mocking setup
├── pytest.ini          # Test configuration and markers
├── test_*.py           # Individual test modules
└── README.md           # This documentation
```

## AI-Assisted Test Development

### Adding New Unit Tests with AI

When you need to create tests for a new utility module, use this AI prompt template:

```
I need to create comprehensive unit tests for the utilities/{module_name}.py module.
First create only a plan.

Please analyze the module and create a test file following these requirements:

1. **File Structure**: Create `test_{module_name}.py` in utilities/unittests/
2. **Test Class**: Use class-based organization with `TestClassName` format
3. **Mocking Strategy**: Follow the existing patterns in conftest.py for mocking external dependencies
4. **Coverage Goals**: Test all public functions, edge cases, and error conditions
5. **Fixtures**: Use existing fixtures from conftest.py where applicable
6. Base code must not be modified
7. Avoid code duplications

The module contains: [briefly describe the main functions/classes]

Please ensure tests are:
- Independent and isolated
- Fast-executing with proper mocking
- Comprehensive in coverage
- Following existing code style
- Well-documented with clear test names
```

Review the plan and ask to modify it if needed.

### Modifying Existing Tests with AI

To enhance or fix existing tests, use this approach:

```
I need to modify the tests in utilities/unittests/test_{module_name}.py to:
[describe specific changes needed]

Current issues/requirements:
- [specific issue 1]
- [specific issue 2]

First create only a plan.

Please:
1. Maintain existing test structure and patterns
2. Preserve working test cases
3. Add new test cases for uncovered scenarios
4. Update mocking if needed
5. Ensure all tests still pass
6. Follow the established naming conventions
7. Base code must not be modified
8. Re-use existing code as much as possible

```

## Coverage

Tests verification and coverage and done via `tox`

```bash
tox -e utilities-unittests
```

## Testing Conventions

### File Naming
- Test files: `test_{module_name}.py`
- Match the utility module name exactly
- Example: `console.py` → `test_console.py`

### Class Organization
```python
class TestModuleName:
    """Test cases for ModuleName class/module"""

    def test_function_name_with_scenario(self):
        """Test specific scenario with clear description"""
```

### Test Method Naming
Use descriptive names that explain what is being tested:
- `test_console_init_with_defaults`
- `test_vm_creation_with_invalid_params`
- `test_network_config_when_missing_namespace`

### Mocking Strategy
Follow these patterns from `conftest.py`:

```python
# Use existing fixtures for common mocks
def test_with_vm_mock(self, mock_vm):
    # Test uses pre-configured VM mock

# Mock external dependencies
@patch('utilities.module.external_function')
def test_with_external_mock(self, mock_external):
    # Test with mocked external call
```

## Test Coverage Goals

### Current Status
✅ **Completed**:
- architecture.py
- bitwarden.py
- console.py
- constants.py
- data_collector.py
- database.py
- exceptions.py
- logger.py
- monitoring.py
- must_gather.py
- os_utils.py
- pytest_matrix_utils.py
- pytest_utils.py
- ssp.py
- vnc_utils.py

🔄 **Remaining Work**:
- hco.py (HyperConverged Operator utilities)
- infra.py (Infrastructure management utilities)
- network.py (Network configuration utilities)
- operator.py (Operator lifecycle utilities)
- storage.py (Storage management utilities)
- virt.py (Virtualization utilities)

### Coverage Requirements
- **Minimum**: 80% line coverage per module
- **Target**: 90% line coverage with edge case testing
- **Critical paths**: 100% coverage for error handling and resource management
