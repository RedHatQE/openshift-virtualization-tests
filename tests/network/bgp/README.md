## BGP Test Infra Overview

BGP tests verify connectivity between the CUDN VM and the external network using BGP.

### External BGP Router

An external BGP router is required for real-world BGP connectivity, as customers typically have a router outside the
cluster. For testing, the router is implemented as a pod running OpenPE (OpenPERouter) host mode within the cluster,
serving the same role as an external router. Multus creates the pod's `net1` attachment and OpenPE creates a DHCP
macvlan child in its own router namespace. The external BGP router (a pod in this case) must be on the same network as
the cluster nodes to enable direct BGP sessions.

The OpenPE image is `quay.io/openperouter/router:main` by default and the test
mounts its host-mode entrypoint from the OpenPE ConfigMap (see
`data/openpe/README.md`). Override with `CNV_EXTERNAL_OPENPE_IMAGE` if needed.
