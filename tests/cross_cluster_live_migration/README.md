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

There are two ways to provide the remote kubeconfig:

#### Option 1: Using CLI argument
```bash
uv run pytest tests/cross_cluster_live_migration/ --remote-kubeconfig=/path/to/remote-cluster-kubeconfig
```

#### Option 2: Using environment variable
```bash
export REMOTE_KUBECONFIG=/path/to/remote-cluster-kubeconfig
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

### Run Specific Test Files

#### Connectivity Tests
Test basic connectivity to the remote cluster:
```bash
# Using CLI argument
uv run pytest tests/cross_cluster_live_migration/test_cross_cluster_connectivity.py -v --remote-kubeconfig=/path/to/remote-kubeconfig.yaml

# Using environment variable
export REMOTE_KUBECONFIG=/path/to/remote-cluster-kubeconfig.yaml
uv run pytest tests/cross_cluster_live_migration/test_cross_cluster_connectivity.py -v
```
