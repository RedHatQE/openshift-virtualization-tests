# Customized Docker image

## Instruction
This document describes how the docker image "qe-cnv-tests-registry-official-cirros" was made,\
which is used in test_import_registry.py.

## Steps


#### 1. Pull official cirros image from dockerhub
```
$ docker pull docker.io/cirros
```

#### 2. Tag the image
```
$ docker tag cirros quay.io/openshift-cnv/qe-cnv-tests-registry-official-cirros
```

#### 3. Push docker image to Quay
Note: Before push, you need to login
```
$ docker login quay.io
```
```
$ docker push quay.io/openshift-cnv/qe-cnv-tests-registry-official-cirros
```
