# Cross-Cluster Live Migration Tests

This directory contains tests for validating live migration of virtual machines between OpenShift clusters running OpenShift Virtualization.

## Prerequisites

### Cluster Requirements
- Two OpenShift clusters with OpenShift Virtualization installed
- Both clusters must have network connectivity between them
- Compatible CPU architectures between clusters

### Network Requirements
- Network connectivity between clusters on migration ports

## Setup

### 1. Remote Cluster Configuration

You need to provide a kubeconfig file for the remote (target) cluster. This should be a separate kubeconfig from your primary cluster.

```bash
# Export the remote cluster kubeconfig to a file
export REMOTE_KUBECONFIG=/path/to/remote-cluster-kubeconfig.yaml
```

### 2. Verify Remote Access

Test that you can access the remote cluster:
```bash
oc --kubeconfig=$REMOTE_KUBECONFIG get nodes
```

## Running Tests

### Run All Cross-Cluster Tests
```bash
uv run pytest tests/cross_cluster_live_migration/ -v
```

### Debugging Tips

1. **Verify Remote Cluster Access**:
   ```bash
   oc --kubeconfig=$REMOTE_KUBECONFIG cluster-info
   ```

2. **Check Available Contexts**:
   ```bash
   oc --kubeconfig=$REMOTE_KUBECONFIG config get-contexts
   ```

3. **Test Basic Operations**:
   ```bash
   oc --kubeconfig=$REMOTE_KUBECONFIG get namespaces
   ```

4. **Validate Permissions**:
   ```bash
   oc --kubeconfig=$REMOTE_KUBECONFIG auth can-i get vms
   oc --kubeconfig=$REMOTE_KUBECONFIG auth can-i create vmim
   ```
