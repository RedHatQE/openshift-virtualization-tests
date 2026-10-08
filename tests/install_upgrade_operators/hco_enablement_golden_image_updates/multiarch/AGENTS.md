# Multiarch Golden Image Tests

Domain-specific guidance for `tests/install_upgrade_operators/hco_enablement_golden_image_updates/multiarch/`.

## HCO Multiarch Metrics Semantics

`kubevirt_hco_dataimportcrontemplate_with_supported_architectures` and
`kubevirt_hco_dataimportcrontemplate_with_architecture_annotation` are **boolean gauges**:

- `1` — the property is present (healthy/correct configuration)
- `0` — the property is absent (misconfiguration detected)

In negative misconfiguration tests (e.g. unsupported architecture annotation, missing annotation),
the expected metric value is **`0`**.
