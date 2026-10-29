#!/bin/sh
# Run OpenPE static host mode with FRR in its normal named router namespace.
set -eu

FRR_DIR=/etc/perouter/frr
FRR_CONF="${FRR_DIR}/frr.conf"
FRR_PID="${FRR_DIR}/frr.pid"
FRR_SOCK="${FRR_DIR}/frr.socket"
ROUTER_NETNS=perouter

log() {
	echo "$(date '+%Y-%m-%dT%H:%M:%S') $*"
}

install_fake_systemctl() {
	# Host-mode readiness checks the router service through systemctl. This
	# single-container test image owns FRR directly, so report that service active.
	cat >/usr/bin/systemctl <<'EOF'
#!/bin/sh
case "$1:${2:-}" in
is-active:routerpod-pod.service)
	echo active
	exit 0
	;;
restart:routerpod-pod.service)
	exit 0
	;;
*)
	exit 0
	;;
esac
EOF
	chmod +x /usr/bin/systemctl
}

mkdir -p "${FRR_DIR}" /var/run/frr /var/run/netns /etc/openperouter/configs
chmod a+rw /var/run/frr || true
touch "${FRR_CONF}"

sysctl -w net.ipv4.ip_forward=1
sysctl -w net.ipv6.conf.all.forwarding=1

if [ ! -e "/var/run/netns/${ROUTER_NETNS}" ]; then
	ip netns add "${ROUTER_NETNS}"
fi
ip netns exec "${ROUTER_NETNS}" ip link set lo up
install_fake_systemctl

log "starting FRR in ${ROUTER_NETNS}"
ip netns exec "${ROUTER_NETNS}" /sbin/tini -s -- /usr/lib/frr/docker-start &
echo $! >"${FRR_PID}"

log "starting reloader in ${ROUTER_NETNS}"
ip netns exec "${ROUTER_NETNS}" /reloader \
	--frrconfig="${FRR_CONF}" \
	--loglevel=debug \
	--unixsocket "${FRR_SOCK}" \
	--bindaddress 0.0.0.0:9080 &
echo $! >/var/run/openpe-reloader.pid

log "starting controller in host mode"
/controller \
	--mode host \
	--namespace openperouter-system \
	--frrconfig "${FRR_CONF}" \
	--pid-path "${FRR_PID}" \
	--reloader-socket "${FRR_SOCK}" \
	--node-config /etc/openperouter/node-config.yaml \
	--host-configuration-dir /etc/openperouter/configs \
	--loglevel debug &
echo $! >/var/run/openpe-controller.pid

cleanup() {
	log "stopping OpenPE children"
	kill "$(cat /var/run/openpe-controller.pid 2>/dev/null)" 2>/dev/null || true
	kill "$(cat /var/run/openpe-reloader.pid 2>/dev/null)" 2>/dev/null || true
	kill "$(cat "${FRR_PID}" 2>/dev/null)" 2>/dev/null || true
}
trap cleanup INT TERM

controller_pid=$(cat /var/run/openpe-controller.pid)
while kill -0 "${controller_pid}" 2>/dev/null; do
	sleep 5
done
log "controller exited"
wait || true
exit 1
