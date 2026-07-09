"""
In-cluster push-mode backup restore client.

Runs as the main process of a push restore pod. Configuration is supplied through
the CBT_PUSH_RESTORE_PARAMS environment variable as a JSON object.

Implements the manual restore workflow from the incremental backup VEP: locate
qcow2 backups on a read-only PVC, rebase incremental chains in checkpoint order,
and convert the merged image to raw on the target boot PVC.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PUSH_RESTORE_PARAMS_ENV = "CBT_PUSH_RESTORE_PARAMS"


def _load_params() -> dict[str, Any]:
    """Load restore parameters from the environment."""
    params_json = os.environ[PUSH_RESTORE_PARAMS_ENV]
    return json.loads(params_json)


# Duplicated in pull_collect_runner.py — both runners are standalone scripts executed
# inside pods and cannot share imports from the test framework.
def _checkpoint_timestamp_from_path(path: str, checkpoint_timestamp_pattern: str) -> str:
    """Return the checkpoint timestamp embedded in a backup qcow2 path."""
    match = re.search(checkpoint_timestamp_pattern, path)
    return match.group(1) if match else ""


def _find_push_backup_qcow2_files(params: dict[str, Any]) -> list[str]:
    """Return qcow2 backup files from the mounted push-mode backup PVC, sorted by checkpoint."""
    backup_dir = str(params["backup_dir"])
    find_result = subprocess.run(
        ["/usr/bin/find", backup_dir, "-name", "*.qcow2", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    qcow2_files = [line.strip() for line in find_result.stdout.splitlines() if line.strip()]
    if not qcow2_files:
        list_result = subprocess.run(
            ["/usr/bin/find", backup_dir, "-type", "f"],
            check=False,
            capture_output=True,
            text=True,
        )
        raise RuntimeError(f"No qcow2 files under {backup_dir}. Files:\n{list_result.stdout}")
    checkpoint_timestamp_pattern = str(params["checkpoint_timestamp_pattern"])
    return sorted(
        qcow2_files,
        key=lambda path: _checkpoint_timestamp_from_path(
            path=path,
            checkpoint_timestamp_pattern=checkpoint_timestamp_pattern,
        ),
    )


def _run_qemu_img(command_args: list[str]) -> None:
    """Run qemu-img with the given arguments."""
    subprocess.run(["qemu-img", *command_args], check=True)


def _convert_qcow2_to_raw(*, source_qcow2: str, target_file: str) -> None:
    """Convert one qcow2 backup file to a raw disk image."""
    _run_qemu_img(command_args=["convert", "-f", "qcow2", "-O", "raw", source_qcow2, target_file])


def _copy_qcow2_chain_to_workdir(
    *,
    qcow2_files: list[str],
    volume_work_dir: str,
) -> list[str]:
    """
    Copy qcow2 chain files to a writable work directory.

    Incremental images reference virt-launcher backing paths that are not available
    on the read-only backup PVC mount.
    """
    os.makedirs(volume_work_dir, exist_ok=True)
    work_files: list[str] = []
    for file_index, qcow2_file in enumerate(qcow2_files):
        work_path = str(Path(volume_work_dir) / f"chain-{file_index}-{Path(qcow2_file).name}")
        subprocess.run(["cp", qcow2_file, work_path], check=True)
        work_files.append(work_path)
    return work_files


def _rebase_incremental_chain(work_files: list[str]) -> str:
    """Rebase an incremental qcow2 chain in VEP order and return the merged top image."""
    base_image = work_files[0]
    for work_file in work_files[1:]:
        _run_qemu_img(command_args=["rebase", "-b", base_image, "-F", "qcow2", "-f", "qcow2", "-u", work_file])
        base_image = work_file
    return base_image


def _restore_incremental_chain(
    *,
    qcow2_files: list[str],
    volume_work_dir: str,
    target_file: str,
) -> None:
    """Copy, rebase, and convert an incremental qcow2 chain to raw."""
    work_files = _copy_qcow2_chain_to_workdir(
        qcow2_files=qcow2_files,
        volume_work_dir=volume_work_dir,
    )
    merged_qcow2 = _rebase_incremental_chain(work_files=work_files)
    _convert_qcow2_to_raw(source_qcow2=merged_qcow2, target_file=target_file)


def _assert_target_written(*, target_file: str) -> None:
    """Fail if the restore target was not written.

    Block devices are always present as device nodes; for those targets the
    convert step itself is the write. Filesystem targets must be a non-empty file.
    """
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
    """Restore push-mode qcow2 backup data to a raw boot disk file."""
    params = _load_params()
    target_file = str(params["target_file"])
    volume_work_dir = str(params["volume_work_dir"])
    qcow2_files = _find_push_backup_qcow2_files(params=params)
    print(
        f"Push restore: found {len(qcow2_files)} qcow2 file(s) under {params['backup_dir']}",
        flush=True,
    )
    if len(qcow2_files) == 1:
        _convert_qcow2_to_raw(source_qcow2=qcow2_files[0], target_file=target_file)
    else:
        _restore_incremental_chain(
            qcow2_files=qcow2_files,
            volume_work_dir=volume_work_dir,
            target_file=target_file,
        )
    _assert_target_written(target_file=target_file)
    print(f"Push restore complete: wrote {target_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as process_error:
        print(f"Push restore command failed: {process_error}", file=sys.stderr, flush=True)
        raise
