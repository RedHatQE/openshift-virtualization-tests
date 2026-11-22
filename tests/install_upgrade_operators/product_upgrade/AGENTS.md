# Product Upgrade Tests

Domain-specific guidance for `tests/install_upgrade_operators/product_upgrade/`.

## EUS Upgrade CLI Option

The `--eus-ocp-images` option validation in the root `conftest.py` intentionally checks only
token count (`len == 2`) rather than validating the image URLs themselves. This is deliberate:
the tox collection command passes placeholder tokens (`NA,NA`) with
`--collect-only`; collection skips this validation, so no real image URLs
are needed.
Do not tighten this check to validate URL format — it would break CI.
