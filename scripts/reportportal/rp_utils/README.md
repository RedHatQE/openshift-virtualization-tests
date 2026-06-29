<!-- Co-authored-by: Claude <noreply@anthropic.com> -->
# ReportPortal Shared Utilities

Shared library used by `rp_manual_reporter`.

---

## Modules

### `rp_client.py` — RPClient

Thread-safe HTTP client for the ReportPortal REST API. Handles authentication,
pagination, and launch/item CRUD operations.

```python
from scripts.reportportal.rp_utils.rp_client import RPClient

client = RPClient(
    base_url="https://reportportal.example.com",
    project="my-project",
    token="my-api-token",
)
```

#### API

| Method | Returns | Description |
|--------|---------|-------------|
| `get_launches(bundle_prefix)` | `list[dict]` | Fetch launches whose BUNDLE attribute value **contains** `bundle_prefix` (uses RP `filter.cnt.attributeValue`) |
| `get_test_items(launch_id)` | `list[dict]` | Fetch all STEP-level test items for a launch |
| `create_launch(name, attributes, description)` | `str` (UUID) | Start a new launch, returns launch UUID |
| `finish_launch(launch_uuid)` | `None` | Finish a launch |
| `start_test_item(launch_uuid, name, description, attributes)` | `str` (UUID) | Start a test item under a launch, returns item UUID |
| `finish_test_item(item_uuid, status, issue)` | `None` | Finish a test item with status and optional defect issue |
| `update_launch(launch_id, attributes, description)` | `None` | Update launch attributes (uses numeric launch ID) |

#### Pagination

`get_launches()` and `get_test_items()` automatically paginate through all results
using the RP filter API. Page size defaults to 300 items.

---

### `naming.py` — Node ID Conversion

Converts pytest node IDs to ReportPortal test item names.

```python
from scripts.reportportal.rp_utils.naming import node_id_to_rp_name

rp_name = node_id_to_rp_name(node_id="tests/network/test_foo.py::TestBar::test_baz[param1]")
# Returns: "tests.network.test_foo.TestBar.test_baz[param1]"
```

The conversion replaces path separators (`/`) and pytest separators (`::`) with dots,
while preserving parameter suffixes (`[...]`) unchanged.

---

## Running Tests

```bash
uv run tox -e rp-utils-tests
```
