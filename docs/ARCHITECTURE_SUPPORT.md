# Test Images Architecture Support

The tests can dynamically select test images based on the system's architecture.
This is controlled by the environment variable `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH`.
Note: to run on the default architecture `x86_64`, there's no need to set the environment variable.

Supported architectures include:

- `x86_64` (default)
- `arm64`
- `s390x` (currently work in progress)

Ensure the environment variable is set correctly before running the tests:

```bash
export OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH=<desired-architecture>
```

## Test markers and global_config
To run tests on a specific architecture, add the path to the relevant `global_config` file and add `-m <architecture>` to the pytest command.

For example:

```bash
pytest  --tc-file=tests/global_config_x86.py
pytest -m arm64  --tc-file=tests/global_config_arm64.py ...
pytest -m s390x  --tc-file=tests/global_config_s390x.py ...
```

Note: to run on the default architecture `x86_64`, there's no need to set any architecture-specific markers.

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
  - The file should contain the relevant os matrix(es); see [global_config_x86.py](../tests/global_config_x86.py) for an example
- Add the architecture name as a constant under [constants.py](../utilities/constants.py)
- Add the architecture name to the list of supported architectures under [get_test_images_arch_class](../utilities/constants.py)
- Add the architecture name to the `ArchImages` under the relevant architecture and OS under [constants.py](../utilities/constants.py)
