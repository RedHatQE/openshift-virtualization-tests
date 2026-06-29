# Co-authored-by: Claude <noreply@anthropic.com>
"""Shared test bootstrap for ReportPortal test packages.

Sets ``OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH`` early enough that
module-level imports in ``cluster_info.py`` can resolve without a live
cluster connection.  Snapshot/restore is handled by the fixture so the
process-global state is left clean after the test session.
"""

from __future__ import annotations

import os

# Snapshot BEFORE any mutation so teardown can restore faithfully.
ORIGINAL_ARCH: str | None = os.environ.get("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH")

# Set immediately at import time — must happen before pytest collection
# triggers module-level imports that call get_cluster_architecture().
os.environ.setdefault("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", "amd64")
