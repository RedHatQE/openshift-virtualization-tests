# CNV-QE-network

## VM Network Interface Terminology

### Two-Layer Model

A VM network interface involves two distinct, independent layers:

1. **CNI** — the Kubernetes pod-level plugin that configures the pod's network interface
2. **Network binding** — the KubeVirt mechanism that wires the VM's interface through the pod interface to the node

### Standard Phrasing

When both layers need to be stated explicitly:

```
<primary/secondary> network using <binding> network binding to connect to the node through <CNI> CNI
```

### Known Combinations

The following are established combinations in this project. Use the shorthand name in STD docstrings — spelling out binding and CNI is not required unless the test is specifically about that layer.

| Shorthand | Primary/Secondary | Binding | CNI |
|-----------|-------------------|---------|-----|
| localnet | secondary | bridge | OVN-K |
| Linux bridge | secondary | bridge | Linux Bridge |
| UDN | primary | l2bridge plugin | OVN-K |
| pod network | primary | masquerade | OVN-K |
| SR-IOV | secondary | SR-IOV | SR-IOV |

Binding and CNI may be omitted when the combination is unambiguous from context (e.g., the test directory name already implies the CNI). The full standard phrasing is required when the combination is non-standard, novel, or when clarity demands it.

---

## General Configurations

### VLAN
The current supported vlan tags range in RH labs is 1000-1019.

On IBM clusters the tags can vary they should be transferred as a pytest argument like so:

--tc=vlans:861,978,1138
