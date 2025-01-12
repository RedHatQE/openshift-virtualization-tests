# Customized Docker image

## Instruction
This document describes how the docker image "qe-cnv-tests-registry-fedora29-qcow2-rootdir" was made,\
which is used in test_import_registry.py.

The image requires three conditions:
1. The disk image file is not under /disk directory
2. It's qcow2 format.
3. The name can be anything except disk.img

So it's a invalid image.

## Steps

#### 1. Get a fedora image

#### 2. Convert image to qcow2
```
$ qemu-img convert -c -O qcow2 $IMAGE $BUILD_DIR/fedora29.qcow2
```

#### 3. Create a Dockerfile
```
$ echo "FROM kubevirt/container-disk-v1alpha" >> $BUILD_DIR/Dockerfile
$ echo "ADD fedora29.qcow2 /root" >> $BUILD_DIR/Dockerfile
```

#### 4. Build docker image
```
$ docker build -t fedora29:$VERSION .
```

#### 5. Tag docker image
``
$ docker tag fedora29:$VERSION quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir
``

#### 6. Push docker image to Quay
Note: Before push, you need to login
```
$ docker login quay.io
```
```
$ docker push quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir
```

#### 7. Validate the docker image
```
$ docker pull quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir
$ docker run -it quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir bash
```
In docker container, there should be a fedora29.qcow2 in /root directory
