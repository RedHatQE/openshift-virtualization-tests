"""OS test matrix parameter keys.

String keys used in common-templates test parametrization dictionaries.
Each constant names a field in a test parameter dict (image path, DV size, OS version, etc.).

Not for instance type or preference name strings — those go in `instance_types.py`.
"""

IMAGE_NAME_STR = "image_name"
IMAGE_PATH_STR = "image_path"
CONTAINER_DISK_IMAGE_PATH_STR = "container_disk_image_path"
DV_SIZE_STR = "dv_size"
TEMPLATE_LABELS_STR = "template_labels"
LATEST_RELEASE_STR = "latest_released"
OS_VERSION_STR = "os_version"
DATA_SOURCE_STR = "data_source"
