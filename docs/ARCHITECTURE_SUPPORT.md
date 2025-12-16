# Test Images Architecture Support

The tests can dynamically select test images based on the system's architecture.
By default, the architecture is extracted from the cluster nodes' `arch` label.
For CI, or to run `--collect-only` without cluster access, this is controlled by the environment variable `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH`.
Note: to run on the default architecture `amd64`, there's no need to set the environment variable.

Supported architectures include (names aligned with Kubernetes/KubeVirt):

- `amd64` (default, also refered to as x86_64)
- `arm64`
- `s390x` (currently work in progress)

## Heterogeneous (multi-arch) clusters

On clusters with nodes of different CPU architectures, you must pass `--cpu-arch` to select which architecture to run tests for (e.g. `--cpu-arch=amd64` or `--cpu-arch=arm64`). Use the config file `tests/global_config_multiarch.py` and the `multiarch` marker for tests that run across multiple architectures. Do not pass `--cpu-arch` on homogeneous clusters.

## Test markers
To run tests on a specific architecture, add `-m <architecture>` to the pytest command.

For example:

```bash
pytest -m arm64 ...
pytest -m s390x ...
```

Note: to run on the default architecture `amd64`, there's no need to set any architecture-specific markers.

## Adding new images or new architecture support
Images for different architectures are managed under [constants.py](../utilities/constants.py) - `ArchImages`
The data structures are defined under [images.py](../libs/infra/images.py)

### Adding new images
To add a new image:
- Add the image name under the relevant dataclass under [images.py](../libs/infra/images.py)
- Add the image name to the `ArchImages` under the relevant architecture and OS under [constants.py](../utilities/constants.py)
- Add the image to the image mapping under [os_utils.py](../utilities/os_utils.py); refer to existing images for the format

### Adding new architecture support
To add a new architecture:
- Add the architecture name to the `ARCHITECTURE_SUPPORT` list under [ARCHITECTURE_SUPPORT.md](ARCHITECTURE_SUPPORT.md)
- Add a new pytest marker for the architecture
- Add a new pytest global config file for the architecture under [tests/global_config_<architecture>.py](../tests/global_config_<architecture>.py)
  - The file should contain the relevant OS matrix(es); see [global_config_amd64.py](../tests/global_config_amd64.py) for an example
- Add the architecture name as a constant under [constants.py](../utilities/constants.py)
- Add the architecture name to the list of supported architectures under [get_test_images_arch_class](../utilities/constants.py)
- Add the architecture name to the `ArchImages` under the relevant architecture and OS under [constants.py](../utilities/constants.py)
