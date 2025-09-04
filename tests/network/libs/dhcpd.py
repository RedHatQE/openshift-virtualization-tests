import shlex

from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_5SEC, TIMEOUT_30SEC
from utilities.network import LOGGER
from utilities.virt import VirtualMachineForTests

DHCP_IP_SUBNET = "10.200.3"
DHCP_IP_RANGE_START = f"{DHCP_IP_SUBNET}.3"
DHCP_IP_RANGE_END = f"{DHCP_IP_SUBNET}.10"
DHCP_SERVICE_RESTART = "sudo systemctl restart dhcpd"
DHCP_SERVER_CONF_FILE = """
cat <<EOF >> /etc/dhcp/dhcpd.conf
default-lease-time 3600;
max-lease-time 7200;
authoritative;
subnet {DHCP_IP_SUBNET}.0 netmask 255.255.255.0 {{
  option subnet-mask 255.255.255.0;
  option routers {DHCP_IP_SUBNET}.1;
  option domain-name-servers {DHCP_IP_SUBNET}.1;

  pool {{
    range {DHCP_IP_RANGE_START} {DHCP_IP_RANGE_END};
    allow known-clients;
    deny  unknown-clients;
  }}
}}
host intended_client_vm {{
  hardware ethernet {CLIENT_MAC_ADDRESS};
}}
EOF
"""


def verify_dhcpd_activated(vm: VirtualMachineForTests) -> bool:
    active = "active"
    dhcpd = "dhcpd"
    sample = None
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=TIMEOUT_5SEC,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=[shlex.split(f"sudo systemctl is-{active} {dhcpd}")],
    )
    try:
        for sample in sampler:
            if sample[0].strip() == active:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"{dhcpd} status is not '{active}' but rather '{sample}'")
        raise

    return False
