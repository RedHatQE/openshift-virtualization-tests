FROM quay.io/centos/centos:stream9
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "s390x" ] ; then \
      yum install yum-utils -y ; \
      yum-config-manager --add-repo='https://buildlogs.centos.org/centos/9-stream/nfv/s390x/openvswitch-2' ; \
    else \
      yum install epel-release centos-release-nfv-openvswitch -y ; \
    fi ; \
    yum update -y && yum install iproute tcpdump qemu-img NetworkManager xfreerdp xauth xorg-x11-server-Xvfb which nftables stress-ng nmap -y && yum install --nogpgcheck openvswitch3.1 -y && yum clean all
