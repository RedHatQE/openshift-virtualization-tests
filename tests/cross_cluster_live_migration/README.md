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

### Remote Cluster Configuration

You need to provide authentication credentials for the remote (target) cluster. The tests will authenticate to the remote cluster using username and password.

#### Required CLI arguments
```bash
uv run pytest tests/cross_cluster_live_migration/ \
  --remote_cluster_host=https://api.remote-cluster.example.com:6443 \
  --remote_cluster_username=kubeadmin \
  --remote_cluster_password='YOUR_PASSWORD'
```
