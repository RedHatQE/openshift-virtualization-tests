"""Auto-enable coverage measurement in every Python subprocess."""

import os

os.environ.setdefault("COVERAGE_PROCESS_START", ".coveragerc")
try:
    import coverage

    coverage.process_startup()
except ImportError:
    pass
