"""
In-cluster pull-mode client backup restore.

Runs as the main process of a pull restore pod. Configuration is supplied through
the CBT_PULL_RESTORE_PARAMS environment variable as a JSON object.

Selects the latest raw snapshot for a boot volume from client backup storage
(timestamp-ordered, matching pull collect) and copies it to the restore target.
"""

import json
import os
import re
import subprocess
import sys

PULL_RESTORE_PARAMS_ENV = "CBT_PULL_RESTORE_PARAMS"
BACKUP_DIR = "/backup"
VOLUME_MODE_BLOCK = "Block"
CHECKPOINT_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


# Duplicated in pull_collect_runner.py — runners are standalone scripts executed
# inside pods and cannot share imports from the test framework.
def _checkpoint_timestamp_from_path(path: str) -> str:
    """Return the checkpoint timestamp embedded in a backup path."""
    match = CHECKPOINT_TIMESTAMP_PATTERN.search(path)
    if not match:
        raise RuntimeError(f"Backup path {path!r} has no checkpoint timestamp")
    return match.group(1)


def _list_volume_raw_files(volume_name: str) -> list[str]:
    """Return raw backup files for the boot volume, sorted by checkpoint timestamp."""
    volume_backup_dir = f"{BACKUP_DIR}/{volume_name}"
    find_result = subprocess.run(
        ["/usr/bin/find", volume_backup_dir, "-name", "*.raw", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_files = [line.strip() for line in find_result.stdout.splitlines() if line.strip()]
    if not raw_files:
        list_result = subprocess.run(
            ["/usr/bin/find", BACKUP_DIR, "-type", "f"],
            check=False,
            capture_output=True,
            text=True,
        )
        raise RuntimeError(
            f"No raw backup files under {volume_backup_dir}. Files under backup_dir:\n{list_result.stdout}"
        )
    return sorted(raw_files, key=_checkpoint_timestamp_from_path)


def _copy_raw_to_target(*, source_raw: str, target_file: str, volume_mode: str) -> None:
    """Copy a raw snapshot to the restore target (filesystem file or block device)."""
    if volume_mode == VOLUME_MODE_BLOCK:
        subprocess.run(
            ["qemu-img", "convert", "-p", "-O", "raw", source_raw, target_file],
            check=True,
        )
        return
    subprocess.run(["cp", "--sparse=always", source_raw, target_file], check=True)


def main() -> None:
    """Restore the latest pull-mode raw snapshot for a volume to the boot disk target."""
    params = json.loads(os.environ[PULL_RESTORE_PARAMS_ENV])
    target_file = str(params["target_file"])
    volume_mode = str(params["volume_mode"])
    volume_name = str(params["volume_name"])
    raw_files = _list_volume_raw_files(volume_name=volume_name)
    source_raw = raw_files[-1]
    print(
        f"Pull restore: selected {source_raw} from {len(raw_files)} raw file(s) under {BACKUP_DIR}/{volume_name}",
        flush=True,
    )
    _copy_raw_to_target(source_raw=source_raw, target_file=target_file, volume_mode=volume_mode)
    print(f"Pull restore complete: wrote {target_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as process_error:
        print(f"Pull restore command failed: {process_error}", file=sys.stderr, flush=True)
        raise
