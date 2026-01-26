## BGP Test Infra Overview

BGP tests verify connectivity between the CUDN VM and the external network using BGP.

### External BGP Router

An external BGP router is required for real-world BGP connectivity, as customers typically have a router outside the
cluster. For testing, the router is implemented as a pod running FRR within the cluster, serving the same role as an
external router. The external BGP router (a pod in this case) must be on the same network as the cluster nodes
to enable direct BGP sessions.
