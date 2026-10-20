"""In-cluster pull-mode backup client.

Runs as the main process of a collect pod. Parameters arrive in the
CBT_PULL_COLLECT_PARAMS environment variable as JSON.

The script is copied into the pod and cannot import the test framework. It
downloads allocated extents from the backup export onto a raw file on the
client PVC. An incremental collect copies the previous raw file first and
overlays changed extents.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from typing import Any

PULL_COLLECT_PARAMS_ENV = "CBT_PULL_COLLECT_PARAMS"


def _load_params() -> dict[str, Any]:
    """Load collect parameters from the environment."""
    return json.loads(os.environ[PULL_COLLECT_PARAMS_ENV])


def _build_pull_map_url(
    *,
    map_endpoint: str,
    export_token: str,
    scan_offset: int,
    scan_length: int,
) -> str:
    """Return a pull-mode map endpoint URL."""
    return f"{map_endpoint}?x-kubevirt-export-token={export_token}&offset={scan_offset}&length={scan_length}"


def _curl_pull_endpoint(*, endpoint_url: str, pull_ca_cert_path: str) -> tuple[int, str]:
    """Fetch one pull-mode endpoint and return its HTTP status and body."""
    result = subprocess.run(
        ["curl", "-sS", "-L", "--cacert", pull_ca_cert_path, "-w", "\n%{http_code}", endpoint_url],
        capture_output=True,
        text=True,
    )
    body, separator, status_text = result.stdout.rpartition("\n")
    if not separator:
        raise RuntimeError(
            f"Pull endpoint request failed before an HTTP status: exit={result.returncode} stderr={result.stderr}"
        )
    status = int(status_text)
    if result.returncode != 0 and status < 400:
        raise RuntimeError(
            f"Pull endpoint request failed: exit={result.returncode} HTTP {status} stderr={result.stderr}"
        )
    return status, body


def _fetch_pull_data_extents(params: dict[str, Any]) -> tuple[list[tuple[int, int]], int]:
    """Return allocated byte ranges and the offset where the export map ended.

    A filesystem PVC is larger than the disk image it holds. The map endpoint
    answers until the image ends, then returns HTTP 500. That ends the scan.
    """
    data_extents: list[tuple[int, int]] = []
    scan_offset = 0
    disk_size_bytes = int(params["disk_size_bytes"])
    hole_descriptions = {description.lower() for description in params["pull_map_hole_descriptions"]}
    while scan_offset < disk_size_bytes:
        scan_length = min(int(params["pull_map_scan_limit_bytes"]), disk_size_bytes - scan_offset)
        map_url = _build_pull_map_url(
            map_endpoint=str(params["map_endpoint"]),
            export_token=str(params["export_token"]),
            scan_offset=scan_offset,
            scan_length=scan_length,
        )
        status, body = _curl_pull_endpoint(endpoint_url=map_url, pull_ca_cert_path=str(params["pull_ca_cert_path"]))
        if status >= 400:
            if status == 500 and scan_offset > 0 and data_extents:
                print(f"Pull map ended at offset {scan_offset}", flush=True)
                break
            raise RuntimeError(f"Pull map request failed at offset {scan_offset}: HTTP {status} body={body}")
        map_payload = json.loads(body)
        raw_extents = map_payload.get("extents", map_payload.get("regions", []))
        if not isinstance(raw_extents, list):
            raise TypeError(f"Pull map response has no extents list: {map_payload}")
        for raw_extent in raw_extents:
            offset = raw_extent.get("offset", raw_extent.get("start", raw_extent.get("Start")))
            length = raw_extent.get("length", raw_extent.get("Length"))
            description = raw_extent.get("description", raw_extent.get("Description"))
            if offset is None or length is None:
                raise RuntimeError(f"Pull map extent is missing offset or length: {raw_extent}")
            if str(description).lower() not in hole_descriptions:
                data_extents.append((int(offset), int(length)))
        next_offset = map_payload.get("next_offset", map_payload.get("nextOffset"))
        if next_offset is None:
            scan_offset += scan_length
            continue
        next_scan_offset = int(next_offset)
        if next_scan_offset <= scan_offset:
            scan_offset += scan_length
        else:
            scan_offset = next_scan_offset
    if not data_extents:
        raise RuntimeError("Pull map returned no data extents")
    return data_extents, scan_offset


def _iter_download_chunks(data_extents: list[tuple[int, int]], max_chunk_bytes: int) -> list[tuple[int, int]]:
    """Split extents into offset/length downloads no larger than max_chunk_bytes."""
    download_chunks: list[tuple[int, int]] = []
    for extent_offset, extent_length in data_extents:
        chunk_offset = extent_offset
        remaining_bytes = extent_length
        while remaining_bytes > 0:
            chunk_length = min(max_chunk_bytes, remaining_bytes)
            download_chunks.append((chunk_offset, chunk_length))
            chunk_offset += chunk_length
            remaining_bytes -= chunk_length
    return download_chunks


def _list_volume_raw_files(volume_backup_dir: str) -> list[str]:
    """Return raw files for one volume, oldest checkpoint first."""
    result = subprocess.run(
        ["/usr/bin/find", volume_backup_dir, "-name", "*.raw", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _download_chunk(
    *,
    params: dict[str, Any],
    chunk_offset: int,
    chunk_length: int,
    target_file: str,
) -> None:
    """Download one pull-mode data chunk into a raw image file."""
    download_url = (
        f"{params['data_endpoint']}?x-kubevirt-export-token={params['export_token']}"
        f"&offset={chunk_offset}&length={chunk_length}"
    )
    bash_command = (
        "set -o pipefail; "
        f"curl -s -L --fail --cacert {shlex.quote(str(params['pull_ca_cert_path']))} "
        f"{shlex.quote(download_url)} | "
        f"dd of={shlex.quote(target_file)} oflag=seek_bytes seek={chunk_offset} "
        f"conv=notrunc status=none if=/dev/stdin"
    )
    subprocess.run(["/bin/bash", "-c", bash_command], check=True)


def main() -> None:
    """Collect one pull-mode volume onto client storage."""
    params = _load_params()
    raw_file = str(params["raw_file"])
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    with open(str(params["pull_ca_cert_path"]), "w", encoding="utf-8") as cert_file:
        cert_file.write(str(params["endpoint_cert"]))

    data_extents, image_end = _fetch_pull_data_extents(params=params)
    total_extent_bytes = sum(extent_length for _, extent_length in data_extents)
    download_chunks = _iter_download_chunks(
        data_extents=data_extents,
        max_chunk_bytes=int(params["pull_collect_chunk_size_bytes"]),
    )
    print(
        f"Pull collect map: {len(data_extents)} data extents, "
        f"{total_extent_bytes} extent bytes, {len(download_chunks)} download chunks",
        flush=True,
    )
    if params["enforce_min_collected_bytes"] and total_extent_bytes < int(
        params["pull_full_backup_min_collected_bytes"]
    ):
        raise RuntimeError(
            f"Pull full backup map returned only {total_extent_bytes} data bytes; "
            f"expected at least {params['pull_full_backup_min_collected_bytes']} bytes"
        )

    existing_raw_files = _list_volume_raw_files(volume_backup_dir=str(params["volume_backup_dir"]))
    if not params["force_full_backup"] and existing_raw_files:
        base_raw_file = existing_raw_files[-1]
        print(f"Pull incremental collect: seeding {raw_file} from {base_raw_file}", flush=True)
        subprocess.run(["cp", base_raw_file, raw_file], check=True)
    else:
        subprocess.run(["truncate", "-s", str(image_end), raw_file], check=True)

    for chunk_index, (chunk_offset, chunk_length) in enumerate(download_chunks, start=1):
        if chunk_index == 1 or chunk_index == len(download_chunks) or chunk_index % 10 == 0:
            print(
                f"Pull collect download chunk {chunk_index}/{len(download_chunks)}: "
                f"offset={chunk_offset}, length={chunk_length}",
                flush=True,
            )
        _download_chunk(
            params=params,
            chunk_offset=chunk_offset,
            chunk_length=chunk_length,
            target_file=raw_file,
        )
    print(f"Stored pull backup at {raw_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as process_error:
        print(f"Pull collect command failed: {process_error}", file=sys.stderr, flush=True)
        raise
