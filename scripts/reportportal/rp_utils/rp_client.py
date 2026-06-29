# Co-authored-by: Claude <noreply@anthropic.com>
"""ReportPortal API client for CNV test coverage tools.

Provides authenticated access to the ReportPortal REST API with
automatic pagination support. Used by both the Manual Test Reporter
and the CI Coverage Gate tools.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
import urllib3

LOGGER = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    """Returns current UTC time in ISO format with Z suffix for RP compatibility."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


class RPClient:
    """ReportPortal REST API client with pagination support.

    Args:
        base_url: ReportPortal instance URL (e.g., "https://reportportal.example.com").
        project: RP project name (e.g., "cnv")
        token: Bearer token for authentication
    """

    def __init__(self, base_url: str, project: str, token: str, verify_ssl: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.project = project
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        self.session.verify = verify_ssl
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> RPClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _api_url(self, path: str) -> str:
        """Builds a full API URL for the given resource path.

        Args:
            path: Resource path relative to the project API root.

        Returns:
            Fully qualified API URL.
        """
        return f"{self.base_url}/api/v1/{self.project}/{path}"

    def _paginate(self, url: str, params: dict[str, Any], page_size: int = 300) -> list[dict[str, Any]]:
        """Fetches all pages from a paginated RP endpoint.

        Args:
            url: Full API URL to query.
            params: Query parameters (filters) to include in each request.
            page_size: Number of items per page.

        Returns:
            Accumulated list of content items from all pages.

        Raises:
            requests.HTTPError: If any page request returns a non-2xx status.
        """
        all_items: list[dict[str, Any]] = []
        page_num = 1
        total_pages = 1

        while page_num <= total_pages:
            paginated_params = {**params, "page.size": page_size, "page.page": page_num}
            response = self.session.get(url=url, params=paginated_params, timeout=30)
            response.raise_for_status()
            data = response.json()

            try:
                total_pages = data["page"]["totalPages"]
            except (KeyError, TypeError) as exc:
                raise requests.HTTPError(f"Unexpected RP response format: {exc}") from exc
            LOGGER.info(f"Fetching page {page_num}/{total_pages} from {url}")

            all_items.extend(data.get("content", []))
            page_num += 1

        return all_items

    def create_launch(self, name: str, attributes: list[dict[str, str]], description: str = "") -> str:
        """Creates a new launch in ReportPortal.

        Args:
            name: Launch name.
            attributes: List of attribute dicts (e.g., [{"key": "BUNDLE", "value": "4.19"}]).
            description: Optional launch description.

        Returns:
            The created launch UUID.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = self._api_url(path="launch")
        body = {
            "name": name,
            "startTime": _utc_now_iso(),
            "attributes": attributes,
            "description": description,
            "mode": "DEFAULT",
        }
        response = self.session.post(url=url, json=body, timeout=30)
        response.raise_for_status()
        try:
            launch_uuid = response.json()["id"]
        except (KeyError, TypeError) as exc:
            raise requests.HTTPError(f"Unexpected RP response creating launch: {exc}") from exc
        LOGGER.info(f"Created launch '{name}' with UUID {launch_uuid}")
        return launch_uuid

    def finish_launch(self, launch_uuid: str) -> None:
        """Finishes an existing launch.

        Args:
            launch_uuid: UUID of the launch to finish.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = self._api_url(path=f"launch/{launch_uuid}/finish")
        body = {"endTime": _utc_now_iso()}
        response = self.session.put(url=url, json=body, timeout=30)
        response.raise_for_status()
        LOGGER.info(f"Finished launch {launch_uuid}")

    def start_test_item(
        self,
        launch_uuid: str,
        name: str,
        description: str = "",
        attributes: list[dict[str, str]] | None = None,
    ) -> str:
        """Start a test item (step) within a launch.

        The item is created in an "in progress" state. Call
        ``finish_test_item`` to set the final status and end time.

        Args:
            launch_uuid: Parent launch UUID.
            name: Test item name.
            description: Optional item description.
            attributes: Optional list of attribute dicts.

        Returns:
            The created test item UUID.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = self._api_url(path="item")
        body: dict[str, Any] = {
            "launchUuid": launch_uuid,
            "name": name,
            "type": "STEP",
            "startTime": _utc_now_iso(),
            "hasStats": True,
            "description": description,
        }
        if attributes is not None:
            body["attributes"] = attributes

        response = self.session.post(url=url, json=body, timeout=30)
        response.raise_for_status()
        try:
            item_uuid = response.json()["id"]
        except (KeyError, TypeError) as exc:
            raise requests.HTTPError(f"Unexpected RP response starting test item: {exc}") from exc
        LOGGER.info(f"Started test item '{name}'")
        return item_uuid

    def finish_test_item(
        self,
        item_uuid: str,
        status: str,
        issue: dict[str, str] | None = None,
    ) -> None:
        """Finish a test item with a final status.

        Args:
            item_uuid: UUID of the item to finish.
            status: Final test status (e.g., ``PASSED``, ``FAILED``).
            issue: Optional issue dict for defect linking.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = self._api_url(path=f"item/{item_uuid}")
        body: dict[str, Any] = {
            "endTime": _utc_now_iso(),
            "status": status.upper(),
        }
        if issue is not None:
            body["issue"] = issue

        response = self.session.put(url=url, json=body, timeout=30)
        response.raise_for_status()
        LOGGER.info(f"Finished test item {item_uuid} with status {status.upper()}")

    def get_launches(self, bundle_prefix: str, since_days: int = 0, page_size: int = 300) -> list[dict[str, Any]]:
        """Fetches launches filtered by BUNDLE attribute prefix.

        Args:
            bundle_prefix: Prefix to match against BUNDLE attribute values.
            since_days: Only fetch launches from the last N days (0 = all).
            page_size: Number of items per page.

        Returns:
            List of launch dicts matching the filter.
        """
        url = self._api_url(path="launch")
        params: dict[str, Any] = {
            "filter.has.attributeKey": "BUNDLE",
            "filter.cnt.attributeValue": bundle_prefix,
        }
        if since_days > 0:
            since_ts = int((datetime.now(tz=UTC) - timedelta(days=since_days)).timestamp() * 1000)
            params["filter.gte.startTime"] = since_ts
            LOGGER.info(f"Filtering launches to last {since_days} days")
        launches = self._paginate(url=url, params=params, page_size=page_size)
        LOGGER.info(f"Found {len(launches)} launches matching bundle prefix '{bundle_prefix}'")
        return launches

    def get_test_items(self, launch_id: int, page_size: int = 300) -> list[dict[str, Any]]:
        """Fetches all test items for a given launch.

        Args:
            launch_id: Launch ID to fetch items for.
            page_size: Number of items per page.

        Returns:
            List of test item dicts.
        """
        url = self._api_url(path="item")
        params: dict[str, Any] = {"filter.eq.launchId": launch_id}
        return self._paginate(url=url, params=params, page_size=page_size)

    def update_launch(self, launch_id: int, attributes: list[dict[str, str]], description: str = "") -> None:
        """Updates an existing launch's attributes and description.

        Args:
            launch_id: ID of the launch to update.
            attributes: New list of attribute dicts.
            description: Updated description.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = self._api_url(path=f"launch/{launch_id}/update")
        body = {
            "attributes": attributes,
            "description": description,
            "mode": "DEFAULT",
        }
        response = self.session.put(url=url, json=body, timeout=30)
        response.raise_for_status()
        LOGGER.info(f"Updated launch {launch_id}")
