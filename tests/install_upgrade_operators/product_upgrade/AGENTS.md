# Product Upgrade Tests

Domain-specific guidance for `tests/install_upgrade_operators/product_upgrade/`.

## EUS Upgrade CLI Option

The `--eus-ocp-images` option validation in the root `conftest.py` intentionally checks only
token count (`len == 2`) rather than validating the image URLs themselves. This is deliberate:
tox CI passes placeholder tokens (`NA,NA`) to satisfy the validator without providing real images.
Do not tighten this check to validate URL format — it would break CI.
