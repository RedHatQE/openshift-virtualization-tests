"""In-cluster pull-mode backup restore.

Runs as the main process of a restore pod. Parameters arrive in the
CBT_PULL_RESTORE_PARAMS environment variable as JSON.

The script is copied into the pod and cannot import the test framework. It
copies the newest raw snapshot for one volume from client backup storage onto
the restore target. Collect stores checkpoints in zero-padded directory names,
so path order is backup order.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PULL_RESTORE_PARAMS_ENV = "CBT_PULL_RESTORE_PARAMS"
VOLUME_MODE_BLOCK = "Block"


def _load_params() -> dict[str, Any]:
    """Load restore parameters from the environment."""
    return json.loads(os.environ[PULL_RESTORE_PARAMS_ENV])


def _list_volume_raw_files(params: dict[str, Any]) -> list[str]:
    """Return raw backup files for one volume, oldest checkpoint first."""
    volume_backup_dir = str(Path(str(params["backup_dir"])) / str(params["volume_name"]))
    find_result = subprocess.run(
        ["/usr/bin/find", volume_backup_dir, "-name", "*.raw", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_files = sorted(line.strip() for line in find_result.stdout.splitlines() if line.strip())
    if not raw_files:
        list_result = subprocess.run(
            ["/usr/bin/find", str(params["backup_dir"]), "-type", "f"],
            check=False,
            capture_output=True,
            text=True,
        )
        raise RuntimeError(
            f"No raw backup files under {volume_backup_dir}. Files under backup_dir:\n{list_result.stdout}"
        )
    return raw_files


def _copy_raw_to_target(*, source_raw: str, target_file: str, volume_mode: str) -> None:
    """Copy a raw snapshot onto a filesystem file or a block device."""
    if volume_mode == VOLUME_MODE_BLOCK:
        subprocess.run(["qemu-img", "convert", "-p", "-O", "raw", source_raw, target_file], check=True)
        return
    subprocess.run(["cp", "--sparse=always", source_raw, target_file], check=True)


def _assert_target_written(target_file: str) -> None:
    """Fail when the restore target is missing or empty."""
    target_path = Path(target_file)
    if target_path.is_block_device():
        size_result = subprocess.run(
            ["blockdev", "--getsize64", target_file],
            check=True,
            capture_output=True,
            text=True,
        )
        target_size = int(size_result.stdout.strip())
        if target_size <= 0:
            raise RuntimeError(f"Block restore target {target_file} has size {target_size}")
        return
    if not target_path.is_file() or target_path.stat().st_size == 0:
        raise RuntimeError(f"Filesystem restore target {target_file} is missing or empty")


def main() -> None:
    """Restore the newest pull-mode raw snapshot for one volume."""
    params = _load_params()
    target_file = str(params["target_file"])
    raw_files = _list_volume_raw_files(params=params)
    source_raw = raw_files[-1]
    print(
        f"Pull restore: selected {source_raw} from {len(raw_files)} raw file(s) for volume {params['volume_name']}",
        flush=True,
    )
    _copy_raw_to_target(source_raw=source_raw, target_file=target_file, volume_mode=str(params["volume_mode"]))
    _assert_target_written(target_file=target_file)
    print(f"Pull restore complete: wrote {target_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as process_error:
        print(f"Pull restore command failed: {process_error}", file=sys.stderr, flush=True)
        raise
