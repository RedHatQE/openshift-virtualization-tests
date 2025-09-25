## BGP Test Infra Overview

BGP tests verify connectivity between the CUDN VM and the external network using BGP.

### External BGP Router

An external BGP router is required for real-world BGP connectivity, as customers typically have a router outside the
cluster. For testing, the router is implemented as a pod running FRR within the cluster, serving the same role as an
external router. The external BGP router (a pod in this case) must be on the same network as the cluster nodes
to enable direct BGP sessions.

### Cluster Requirements

The current implementation requires:
- Each node must have at least two NICs.
- All secondary NICs must be connected to the same VLAN as the main IP of the `br-ex` interface.

### Environment Variables

Set these before running tests:

- `PRIMARY_NODE_NETWORK_VLAN_TAG`: the VLAN number of the `br-ex` main IP. Setting this variable implies that a cluster
                                   reflects the requirements mentioned above.
- `EXTERNAL_FRR_STATIC_IPV4`: reserved IPv4 in CIDR format for the external FRR pod (e.g., 192.0.2.10/24)
                              within the PRIMARY_NODE_NETWORK_VLAN_TAG network.

```bash
export PRIMARY_NODE_NETWORK_VLAN_TAG=<vlan_id>
export EXTERNAL_FRR_STATIC_IPV4=<static_ip_cidr>
```
