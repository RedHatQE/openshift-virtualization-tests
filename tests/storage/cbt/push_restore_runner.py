"""In-cluster push-mode backup restore.

Runs as the main process of a restore pod. Parameters arrive in the
CBT_PUSH_RESTORE_PARAMS environment variable as JSON.

The script is copied into the pod and cannot import the test framework.
It uses the container's qemu-img to rebase an incremental qcow2 chain and
convert the merged image onto the target disk.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PUSH_RESTORE_PARAMS_ENV = "CBT_PUSH_RESTORE_PARAMS"


def _load_params() -> dict[str, Any]:
    """Load restore parameters from the environment."""
    return json.loads(os.environ[PUSH_RESTORE_PARAMS_ENV])


def _run_qemu_img(command_args: list[str]) -> None:
    """Run qemu-img and raise if it fails."""
    subprocess.run(["qemu-img", *command_args], check=True)


def _list_qcow2_files(backup_dir: str) -> list[str]:
    """Return every qcow2 file under the backup mount."""
    find_result = subprocess.run(
        ["/usr/bin/find", backup_dir, "-name", "*.qcow2", "-type", "f"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in find_result.stdout.splitlines() if line.strip()]


def _files_for_backup(
    qcow2_files: list[str],
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
) -> list[str]:
    """Return qcow2 files whose path identifies one backup in the chain.

    The backup directory name contains the backup CR name or the checkpoint name,
    but it is not always exactly equal to either one.
    """
    matched = [path for path in qcow2_files if backup_name in path or checkpoint_name in path]
    vm_matched = [path for path in matched if vm_name in path]
    if vm_matched:
        return vm_matched
    return matched


def _select_volume_qcow2(
    *,
    backup_dir: str,
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
    volume_name: str,
    qcow2_files: list[str],
) -> str:
    """Return the qcow2 file for one volume in one backup."""
    exact_candidates = [
        f"{backup_dir}/{vm_name}/{backup_name}/{volume_name}.qcow2",
        f"{backup_dir}/{vm_name}/{checkpoint_name}/{volume_name}.qcow2",
        f"{backup_dir}/{backup_name}/{volume_name}.qcow2",
        f"{backup_dir}/{checkpoint_name}/{volume_name}.qcow2",
    ]
    for candidate in exact_candidates:
        if os.path.isfile(candidate):
            return candidate
    matched = _files_for_backup(
        qcow2_files=qcow2_files,
        vm_name=vm_name,
        backup_name=backup_name,
        checkpoint_name=checkpoint_name,
    )
    exact_names = [path for path in matched if Path(path).stem == volume_name]
    if len(exact_names) == 1:
        return exact_names[0]
    containing_names = [path for path in matched if volume_name in Path(path).name]
    if len(containing_names) == 1:
        return containing_names[0]
    if len(matched) == 1:
        return matched[0]
    listing = "\n".join(qcow2_files) if qcow2_files else "<none>"
    raise RuntimeError(
        f"Could not find one qcow2 for volume {volume_name} in backup {backup_name} "
        f"(checkpoint {checkpoint_name}). Files:\n{listing}"
    )


def _ordered_qcow2_files(params: dict[str, Any]) -> list[str]:
    """Return the volume's qcow2 chain from oldest backup to newest."""
    backup_dir = str(params["backup_dir"])
    qcow2_files = _list_qcow2_files(backup_dir=backup_dir)
    if not qcow2_files:
        list_result = subprocess.run(
            ["/usr/bin/find", backup_dir, "-type", "f"],
            check=False,
            capture_output=True,
            text=True,
        )
        raise RuntimeError(f"No qcow2 files under {backup_dir}. Files:\n{list_result.stdout}")
    return [
        _select_volume_qcow2(
            backup_dir=backup_dir,
            vm_name=str(params["vm_name"]),
            backup_name=str(chain_entry["backup_name"]),
            checkpoint_name=str(chain_entry["checkpoint_name"]),
            volume_name=str(params["volume_name"]),
            qcow2_files=qcow2_files,
        )
        for chain_entry in params["chain"]
    ]


def _convert_qcow2_to_raw(*, source_qcow2: str, target_file: str) -> None:
    """Convert one qcow2 file to a raw disk image."""
    _run_qemu_img(command_args=["convert", "-f", "qcow2", "-O", "raw", source_qcow2, target_file])


def _copy_qcow2_chain_to_workdir(*, qcow2_files: list[str], volume_work_dir: str) -> list[str]:
    """Copy a qcow2 chain onto writable storage so rebase can retarget backing files."""
    os.makedirs(volume_work_dir, exist_ok=True)
    work_files: list[str] = []
    for file_index, qcow2_file in enumerate(qcow2_files):
        work_path = str(Path(volume_work_dir) / f"chain-{file_index}-{Path(qcow2_file).name}")
        subprocess.run(["cp", qcow2_file, work_path], check=True)
        work_files.append(work_path)
    return work_files


def _rebase_incremental_chain(work_files: list[str]) -> str:
    """Point each incremental image at the previous image and return the newest one."""
    base_image = work_files[0]
    for work_file in work_files[1:]:
        _run_qemu_img(command_args=["rebase", "-b", base_image, "-F", "qcow2", "-f", "qcow2", "-u", work_file])
        base_image = work_file
    return base_image


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
    """Restore one push-mode volume chain onto the target disk."""
    params = _load_params()
    target_file = str(params["target_file"])
    qcow2_files = _ordered_qcow2_files(params=params)
    print(
        f"Push restore: volume {params['volume_name']} chain has {len(qcow2_files)} qcow2 file(s)",
        flush=True,
    )
    if len(qcow2_files) == 1:
        _convert_qcow2_to_raw(source_qcow2=qcow2_files[0], target_file=target_file)
    else:
        work_files = _copy_qcow2_chain_to_workdir(
            qcow2_files=qcow2_files,
            volume_work_dir=str(params["volume_work_dir"]),
        )
        merged_qcow2 = _rebase_incremental_chain(work_files=work_files)
        _convert_qcow2_to_raw(source_qcow2=merged_qcow2, target_file=target_file)
    _assert_target_written(target_file=target_file)
    print(f"Push restore complete: wrote {target_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as process_error:
        print(f"Push restore command failed: {process_error}", file=sys.stderr, flush=True)
        raise
