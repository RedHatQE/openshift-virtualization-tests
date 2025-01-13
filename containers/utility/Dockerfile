FROM quay.io/centos/centos:stream9
RUN yum install epel-release centos-release-nfv-openvswitch -y && yum update -y && yum install iproute tcpdump qemu-img openvswitch3.1 NetworkManager xfreerdp xauth xorg-x11-server-Xvfb which nftables stress-ng nmap -y && yum clean all
