### EVPN Connectivity Tests

Tests cover EVPN integration for OpenShift Virtualization VMs.

STP Reference: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/EVPN.md

### Test Topology

EVPN/BGP testing topology (IPs and worker names are examples; traffic is dual-stack):

```text
+------------------------------------------------------------------------------------------------------+
| OCP cluster                                                                                          |
|                                                                                                      |
|   +---------------------------------------+       +---------------------------------------+          |
|   | VM worker (Leaf 1)                    |       | VM worker (Leaf 2)                    |          |
|   | Node IP: 10.44.245.10                 |       | Node IP: 10.44.245.11                 |          |
|   | FRR-K8s: ASN 64512                    |       | FRR-K8s: ASN 64512                    |          |
|   | OVN VTEP: unmanaged                   |       | OVN VTEP: unmanaged                   |          |
|   +-------------------+-------------------+       +-------------------+-------------------+          |
|                       |                                               |                              |
|   +-------------------+-----------------------------------------------+-------------------+          |
|   | EVPN CUDN                                                                             |          |
|   | Subnet: 10.100.0.0/16    MAC-VRF VNI: 10100 (L2)    IP-VRF VNI: 20102 (L3)            |          |
|   +-------------------+-----------------------------------------------+-------------------+          |
|                       |                                               |                              |
|   +-------------------+-------------------+       +-------------------+-------------------+          |
|   | Test VM                               |       | Reference VM / migration destination  |          |
|   | IP: 10.100.0.5                        |       | IP: 10.100.0.6 (reference VM)         |          |
|   +---------------------------------------+       +---------------------------------------+          |
|                                                                                                      |
|                  eBGP / EVPN control plane (both worker FRR peers)                                   |
|                  VXLAN data plane (between OVN and OpenPERouter VTEPs)                               |
|                                              ^                                                       |
|                                              |                                                       |
|   +------------------------------------------|--------------------------------------------+          |
|   | Provider worker (reserved; no test VMs)  |                                            |          |
|   |                                          v                                            |          |
|   |                             [ configured host parent ]                                |          |
|   |                                          | macvlan                                    |          |
|   |   +--------------------------------------|----------------------------------------+   |          |
|   |   | OpenPERouter-managed "perouter" namespace                                     |   |          |
|   |   |                                      |                                        |   |          |
|   |   |                [ net1: 10.44.245.100/24 ]                                     |   |          |
|   |   |                Stock FRR: ASN 64000                                           |   |          |
|   |   |                VTEP: 198.51.100.50/32                                         |   |          |
|   |   |                                      |                                        |   |          |
|   |   |                  +-------------------+-------------------+                    |   |          |
|   |   |                  |                                       |                    |   |          |
|   |   |       [ vni10100: VXLAN ]                     [ vni20102: VXLAN ]             |   |          |
|   |   |                  |                                       |                    |   |          |
|   |   |          [ br-pe-10100 ]                          [ br-pe-20102 ]             |   |          |
|   |   |                  |                                       |                    |   |          |
|   |   |                  |                               [ vrf-blue ]                 |   |          |
|   |   |                  |                                       |                    |   |          |
|   |   |          [ L2 router veth ]                      [ L3 router veth ]           |   |          |
|   |   |                  |                               GW: 172.27.102.1/24          |   |          |
|   |   +------------------|---------------------------------------|--------------------+   |          |
|   |                      | veth pair                             | veth pair              |          |
|   |   +------------------|----------------+  +-------------------|--------------------+   |          |
|   |   | L2 traffic namespace              |  | L3 traffic namespace                   |   |          |
|   |   |          [ L2 traffic veth ]      |  |          [ L3 traffic veth ]           |   |          |
|   |   | IP: 10.100.0.250/16               |  | IP: 172.27.102.2/24                    |   |          |
|   |   | iperf3 <--> test VM (stretched L2)|  | iperf3 <--> test VM (routed L3)        |   |          |
|   |   +-----------------------------------+  +----------------------------------------+   |          |
|   |                                                                                       |          |
|   |   Privileged traffic helper: creates the traffic namespaces/veths and runs iperf3     |          |
|   |   Stock controller: manages net1, VTEP, bridges, VRF, VXLAN and FRR                   |          |
|   +---------------------------------------------------------------------------------------+          |
|                                                                                                      |
| OLM: OperatorGroup -> Subscription -> CSV -> OpenPERouter CR                                         |
| Topology: Underlay + L2VNI + L3VNI + RawFRRConfig (reconciled by the stock controller)               |
+------------------------------------------------------------------------------------------------------+
```

The traffic namespaces serve the same purpose as in the original tests:
they run iperf3 to send and receive traffic with the VMs. Only their router
attachment changes. OpenPERouter now manages the bridge, VRF, VXLAN devices,
and FRR configuration instead of the test configuring a standalone FRR pod.
The L2 bridge also has OpenPERouter's normal host attachment:
`br-pe-10100 -> pe-e-10100 <-> host-e-10100 -> br-hs-10100`.
The existing traffic namespaces attach directly to the router-side bridge or
VRF; they do not use that host bridge.

### OpenPERouter Installation

The provider router is stock OpenPERouter installed through OLM, like other
OpenShift operators. The test discovers the `openperouter-operator` package
in `openshift-marketplace`, requires its `5.0` channel, and creates an
all-namespaces `OperatorGroup` and an automatically approved `Subscription`
in a test-owned namespace. The downstream catalog must already be available;
the test does not install or remove a shared catalog.

After the CSV succeeds, the test creates the `OpenPERouter` CR named
`openperouter`, selecting one labelled worker. SCC permissions come from the
CSV; no Helm CLI or manual SCC grants are needed. OpenPERouter owns the persistent
`perouter` network namespace and creates its underlay, MAC-VRF bridge, IP-VRF
VRF, VXLAN devices, and FRR configuration from Kubernetes CRDs.

Cleanup removes test traffic namespaces and topology CRs before removing the
`OpenPERouter` CR, Subscription, CSV, OperatorGroup, and test namespace. The test
waits for router devices and managed host bridges/veths to disappear while the
controller is still running, then waits for the stock workloads to terminate
before deleting the CSV.
Existing OpenPERouter installations are rejected rather than modified.
The shared catalog and OLM-installed CRDs are not deleted. OpenPERouter's
persistent namespace and host configuration directories are not manually removed.

The EVPN CUDN uses MAC-VRF VNI `10100` and IP-VRF VNI `20102`. The routed-L3
OpenPERouter VRF is `vrf-blue`. The test peers OpenPERouter with the primary
IPv4 address of every worker except the selected provider worker.

A separate privileged helper pod is pinned to the provider worker and mounts
the host network-namespace directory. It creates synthetic endpoints:

- the L2 endpoint veth is attached to OpenPERouter's `br-pe-10100` bridge;
- the L3 endpoint veth is enslaved to OpenPERouter's `vrf-blue`;
- each endpoint side lives in a unique helper-owned network namespace.

The old standalone `frr-external` pod, custom entrypoint, static host mode, and
pod-local Multus `net1` design are not used by these tests.

### Required Environment

The provider attachment is cluster-specific. The tests intentionally provide
no default parent, address, or VTEP because guessing can move traffic onto the
wrong network or select an unusable address.

```bash
export OPENPE_UNDERLAY_PARENT=<host-parent-interface>
export OPENPE_PROVIDER_IPV4=<provider-address-with-prefix>
export OPENPE_VTEP_CIDR=<routable-ipv4-address>/32
```

`OPENPE_UNDERLAY_PARENT` must name a host interface on the selected provider
worker that can reach the worker FRR addresses on the real underlay.
The host-network diagnostics pod checks that the interface exists directly
on that worker; this check does not require NMState or NodeNetworkState.

`OPENPE_PROVIDER_IPV4` must include its prefix, for example `192.0.2.50/24`,
and must be a usable host address. It cannot be a network or broadcast address.

`OPENPE_VTEP_CIDR` must be a routable IPv4 `/32`, for example
`198.51.100.50/32`, reachable through the underlay BGP peers.

### Attachment Discovery

Before the first run, inspect the worker selected by the `worker_node1`
fixture. The EVPN fixture labels that worker automatically:

```bash
oc debug node/<provider-worker> -- chroot /host sh -c \
  'ip -j route show default; ip -j -4 addr show; ip -d link show; bridge link'
```

Choose a parent that reaches the worker FRR peer addresses. Reserve a static,
non-conflicting provider address and VTEP on that network. DHCP is not used by
these tests because a reproducible static attachment is required.

### Serial Console Stability

Repeated console sessions during dual-stack traffic checks can hit Fedora's
serial-getty start limit. The tests disable that limit only for
`serial-getty@ttyS0.service` inside their VMs and verify the effective setting.
The setting is reapplied after cold restart because container-disk guest changes
do not persist. Deleting the test VMs removes the guest-only configuration;
no cluster nodes or OpenPERouter workloads are changed.

### Validation

The module waits for the underlay address, worker reachability, OpenPERouter
bridge and VRF creation, rendered raw FRR configuration, worker BGP sessions,
and EVPN prefixes. If setup fails, it logs OpenPERouter pod logs, router links,
addresses, routes, VRFs, bridge links and FDB, neighbors, generated FRR
configuration, and BGP/EVPN summaries.
