# OpenPE External ToR Configuration

Runtime configuration for the external OpenPE ToR pod deployed by BGP/EVPN tests.

The tests use `quay.io/openperouter/router:main` and mount `entrypoint.sh` from
the OpenPE ConfigMap. The entrypoint creates OpenPE's normal `perouter` router
namespace; the static configuration creates the router underlay as a DHCP
macvlan child of the Multus-owned `net1` interface.

Override the default image at runtime with `CNV_EXTERNAL_OPENPE_IMAGE`.

`node-config.yaml` is mounted into the pod via the OpenPE ConfigMap.
