FROM quay.io/centos/centos:stream9
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "s390x" ] ; then \
      yum install yum-utils -y ; \
      yum-config-manager --add-repo='https://buildlogs.centos.org/centos/9-stream/nfv/s390x/openvswitch-2' ; \
    else \
        yum install -y epel-release centos-release-nfv-openvswitch; \
    fi; \
    yum -y update && \
    yum install -y \
        NetworkManager \
        dhcp-client \
        iperf3 \
        iproute \
        nftables \
        nmap \
        openvswitch3.1 --nogpgcheck \
        procps-ng \
        qemu-img \
        stress-ng \
        tcpdump \
        which \
        xauth \
        xfreerdp \
        xorg-x11-server-Xvfb && \
    yum clean all && \
    rm -rf /var/cache/yum
