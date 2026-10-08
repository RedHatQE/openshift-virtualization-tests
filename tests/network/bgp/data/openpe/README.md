# OpenPE External ToR Configuration

Runtime configuration for the external OpenPE ToR pod deployed by BGP/EVPN tests.

The OpenPE container image is built separately (includes openperouter PR #752
`--router-netns` support) and published to Quay. Tests use the digest-pinned
default in `tests/network/libs/bgp.py`. Override at runtime with
`CNV_EXTERNAL_OPENPE_IMAGE`.

`node-config.yaml` is mounted into the pod via the OpenPE ConfigMap.
