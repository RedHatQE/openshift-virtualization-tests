# Multi-Architecture (Heterogeneous) Clusters

Currently supported architectures for multi-arch runs: `amd64` and `arm64`.

On clusters where nodes have different CPU architectures, you must pass `--cpu-arch` to select the architecture for the run. Use a single value (e.g. `--cpu-arch=amd64`) or, for tests marked with `multiarch`, a comma-separated list (e.g. `--cpu-arch=amd64,arm64`). Use the config file `tests/global_config_multiarch.py` and the `multiarch` marker for tests that run across multiple architectures. Do not pass `--cpu-arch` on homogeneous clusters.

```bash
uv run pytest --tc-file=tests/global_config_multiarch.py --cpu-arch=amd64 ...
```

## Limitations

`*_os_matrix` variables are not created for multi-arch runs (when `--cpu-arch` contains multiple architectures, e.g. `--cpu-arch=amd64,arm64`).
