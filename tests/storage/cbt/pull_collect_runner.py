"""
In-cluster pull-mode backup client.

Runs as the main process of a collect pod. Configuration is supplied through
the CBT_PULL_COLLECT_PARAMS environment variable as a JSON object.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from typing import Any

PULL_COLLECT_PARAMS_ENV = "CBT_PULL_COLLECT_PARAMS"
BACKUP_DIR = "/backup"
PULL_CA_CERT_PATH = "/tmp/backup-ca.crt"
PULL_MAP_SCAN_LIMIT_BYTES = 1 << 30
PULL_COLLECT_CHUNK_SIZE_BYTES = 256 * 1024 * 1024
PULL_MAP_HOLE_DESCRIPTIONS = frozenset({"hole", "zero"})
PULL_FULL_BACKUP_MIN_COLLECTED_BYTES = 100 * 1024 * 1024
CHECKPOINT_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


def _curl_pull_endpoint(*, endpoint_url: str) -> str:
    """Fetch a response from a pull-mode backup endpoint."""
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-L",
            "--fail",
            "--cacert",
            PULL_CA_CERT_PATH,
            endpoint_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _fetch_pull_data_extents(params: dict[str, Any]) -> list[tuple[int, int]]:
    """Return allocated byte ranges from a pull-mode map endpoint."""
    data_extents: list[tuple[int, int]] = []
    scan_offset = 0
    disk_size_bytes = int(params["disk_size_bytes"])
    while scan_offset < disk_size_bytes:
        scan_length = min(PULL_MAP_SCAN_LIMIT_BYTES, disk_size_bytes - scan_offset)
        map_url = (
            f"{params['map_endpoint']}?x-kubevirt-export-token={params['export_token']}"
            f"&offset={scan_offset}&length={scan_length}"
        )
        map_payload = json.loads(_curl_pull_endpoint(endpoint_url=map_url))
        for raw_extent in map_payload["extents"]:
            if str(raw_extent["description"]).lower() not in PULL_MAP_HOLE_DESCRIPTIONS:
                data_extents.append((int(raw_extent["offset"]), int(raw_extent["length"])))
        next_offset = map_payload.get("next_offset")
        if next_offset is not None and int(next_offset) > scan_offset:
            scan_offset = int(next_offset)
        else:
            scan_offset += scan_length
    if not data_extents:
        raise RuntimeError(f"Pull map for {params['map_endpoint']} returned no data extents")
    return data_extents


def _download_chunks(
    data_extents: list[tuple[int, int]],
    max_chunk_bytes: int,
) -> list[tuple[int, int]]:
    """Split extents into offset/length pairs capped at max_chunk_bytes."""
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


# Duplicated in pull_restore_runner.py — runners are standalone scripts executed
# inside pods and cannot share imports from the test framework.
def _checkpoint_timestamp_from_path(path: str) -> str:
    """Return the checkpoint timestamp embedded in a backup path."""
    match = CHECKPOINT_TIMESTAMP_PATTERN.search(path)
    if not match:
        raise RuntimeError(f"Backup path {path!r} has no checkpoint timestamp")
    return match.group(1)


def _list_client_backup_raw_files() -> list[str]:
    """Return sorted raw backup files from pull-mode client storage."""
    result = subprocess.run(
        ["/usr/bin/find", BACKUP_DIR, "-name", "*.raw", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return sorted(raw_files, key=_checkpoint_timestamp_from_path)


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
        f"curl -s -L --fail --cacert {shlex.quote(PULL_CA_CERT_PATH)} "
        f"{shlex.quote(download_url)} | "
        f"dd of={shlex.quote(target_file)} oflag=seek_bytes seek={chunk_offset} "
        f"conv=notrunc status=none if=/dev/stdin"
    )
    subprocess.run(["/bin/bash", "-c", bash_command], check=True)


def main() -> None:
    """Collect pull-mode backup data onto client storage."""
    params = json.loads(os.environ[PULL_COLLECT_PARAMS_ENV])
    raw_file = str(params["raw_file"])
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    with open(PULL_CA_CERT_PATH, "w", encoding="utf-8") as cert_file:
        cert_file.write(str(params["endpoint_cert"]))

    data_extents = _fetch_pull_data_extents(params=params)
    total_extent_bytes = sum(extent_length for _, extent_length in data_extents)
    download_chunks = _download_chunks(
        data_extents=data_extents,
        max_chunk_bytes=PULL_COLLECT_CHUNK_SIZE_BYTES,
    )
    print(
        f"Pull collect map: {len(data_extents)} data extents, "
        f"{total_extent_bytes} extent bytes, {len(download_chunks)} download chunks",
        flush=True,
    )
    if params["force_full_backup"] and total_extent_bytes < PULL_FULL_BACKUP_MIN_COLLECTED_BYTES:
        raise RuntimeError(
            f"Pull full backup map returned only {total_extent_bytes} data bytes; "
            f"expected at least {PULL_FULL_BACKUP_MIN_COLLECTED_BYTES} bytes"
        )

    existing_raw_files = _list_client_backup_raw_files()
    if not params["force_full_backup"] and existing_raw_files:
        # List is ascending by checkpoint timestamp; seed from the newest prior raw so
        # incremental extents (since the previous checkpoint) overlay the right base.
        base_raw_file = existing_raw_files[-1]
        print(
            f"Pull incremental collect: seeding {raw_file} from {base_raw_file}",
            flush=True,
        )
        subprocess.run(["cp", base_raw_file, raw_file], check=True)
    else:
        subprocess.run(["truncate", "-s", str(params["disk_size_bytes"]), raw_file], check=True)

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
