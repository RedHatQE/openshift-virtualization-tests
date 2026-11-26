# Multiarch Golden Image Tests

Domain-specific guidance for `tests/install_upgrade_operators/hco_enablement_golden_image_updates/multiarch/`.

## HCO Multiarch Metrics Semantics

`kubevirt_hco_dataimportcrontemplate_with_supported_architectures` and
`kubevirt_hco_dataimportcrontemplate_with_architecture_annotation` are **boolean gauges**:

- `1` — the configuration is valid and supported (healthy/correct configuration)
- `0` — the property is absent (misconfiguration detected)

In negative misconfiguration tests (e.g. unsupported architecture annotation, missing annotation),
the expected metric value is **`0`**.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:38dcc07e46a94fdf8ca6af1394fe431f8b996ebf77a6d8438855a01b6aaaa193 -->

## Polarion Docstring Migration

Use this format for the one-time migration of Polarion markers to docstrings in these files:

- In `test_multiarch_golden_images_support.py`, list the Polarion IDs for parameter cases together in the test docstring. Do not require per-case annotations or markers solely to preserve those associations.

<!-- /coderabbit-ai-generated:v1 -->
