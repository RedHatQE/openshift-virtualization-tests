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


def _load_params() -> dict[str, Any]:
    """Load collect parameters from the environment."""
    params_json = os.environ[PULL_COLLECT_PARAMS_ENV]
    return json.loads(params_json)


def _build_pull_map_url(
    *,
    map_endpoint: str,
    export_token: str,
    scan_offset: int,
    scan_length: int,
) -> str:
    """Return a pull-mode map endpoint URL using VEP query parameter names."""
    return f"{map_endpoint}?x-kubevirt-export-token={export_token}&offset={scan_offset}&length={scan_length}"


def _curl_pull_endpoint(*, endpoint_url: str, pull_ca_cert_path: str) -> str:
    """Fetch a response from a pull-mode backup endpoint."""
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-L",
            "--fail",
            "--cacert",
            pull_ca_cert_path,
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
    hole_descriptions = {description.lower() for description in params["pull_map_hole_descriptions"]}
    while scan_offset < disk_size_bytes:
        scan_length = min(int(params["pull_map_scan_limit_bytes"]), disk_size_bytes - scan_offset)
        map_url = _build_pull_map_url(
            map_endpoint=str(params["map_endpoint"]),
            export_token=str(params["export_token"]),
            scan_offset=scan_offset,
            scan_length=scan_length,
        )
        map_payload = json.loads(
            _curl_pull_endpoint(
                endpoint_url=map_url,
                pull_ca_cert_path=str(params["pull_ca_cert_path"]),
            )
        )
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
        if next_offset is not None:
            next_scan_offset = int(next_offset)
            if next_scan_offset <= scan_offset:
                scan_offset += scan_length
            else:
                scan_offset = next_scan_offset
        else:
            scan_offset += scan_length
    if not data_extents:
        raise RuntimeError(f"Pull map for {params['map_endpoint']} returned no data extents")
    return data_extents


def _iter_download_chunks(
    data_extents: list[tuple[int, int]],
    max_chunk_bytes: int,
) -> list[tuple[int, int]]:
    """Return offset/length download pairs capped at max_chunk_bytes."""
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


# Duplicated in push_restore_runner.py — both runners are standalone scripts executed
# inside pods and cannot share imports from the test framework.
def _checkpoint_timestamp_from_path(path: str, checkpoint_timestamp_pattern: str) -> str:
    """Return the checkpoint timestamp embedded in a backup path."""
    match = re.search(checkpoint_timestamp_pattern, path)
    return match.group(1) if match else ""


def _list_client_backup_raw_files(params: dict[str, Any]) -> list[str]:
    """Return sorted raw backup files from pull-mode client storage."""
    result = subprocess.run(
        ["/usr/bin/find", str(params["backup_dir"]), "-name", "*.raw", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    checkpoint_timestamp_pattern = str(params["checkpoint_timestamp_pattern"])
    return sorted(
        raw_files,
        key=lambda path: _checkpoint_timestamp_from_path(
            path=path,
            checkpoint_timestamp_pattern=checkpoint_timestamp_pattern,
        ),
    )


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
        f"curl -s -L --fail --cacert {shlex.quote(str(params['pull_ca_cert_path']))} "
        f"{shlex.quote(download_url)} | "
        f"dd of={shlex.quote(target_file)} oflag=seek_bytes seek={chunk_offset} "
        f"conv=notrunc status=none if=/dev/stdin"
    )
    subprocess.run(["/bin/bash", "-c", bash_command], check=True)


def main() -> None:
    """Collect pull-mode backup data onto client storage."""
    params = _load_params()
    raw_file = str(params["raw_file"])
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    with open(str(params["pull_ca_cert_path"]), "w", encoding="utf-8") as cert_file:
        cert_file.write(str(params["endpoint_cert"]))

    data_extents = _fetch_pull_data_extents(params=params)
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
    if params["force_full_backup"] and total_extent_bytes < int(params["pull_full_backup_min_collected_bytes"]):
        raise RuntimeError(
            f"Pull full backup map returned only {total_extent_bytes} data bytes; "
            f"expected at least {params['pull_full_backup_min_collected_bytes']} bytes"
        )

    existing_raw_files = _list_client_backup_raw_files(params=params)
    if not params["force_full_backup"] and existing_raw_files:
        base_raw_file = existing_raw_files[0]
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
