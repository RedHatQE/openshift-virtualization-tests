import pexpect
from timeout_sampler import TimeoutSampler

from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_30SEC, VIRTCTL
from utilities.data_collector import get_data_collector_base_directory


class VNCConnection:
    def __init__(self, vm):
        self.vm = vm
        self.child = None
        self.base_dir = get_data_collector_base_directory()

    def __enter__(self):
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=pexpect.spawn,
            exceptions_dict={pexpect.exceptions.EOF: []},
            command=f"{VIRTCTL} vnc {self.vm.name} --proxy-only  -n {self.vm.namespace}",
            timeout=TIMEOUT_30SEC,
            encoding="utf-8",
        )
        for sample in sampler:
            if sample:
                self.child = sample
                self.child.logfile = open(f"{self.base_dir}/{self.vm.name}.pexpect.log", "a")
                self.child.expect('"port":', timeout=TIMEOUT_5MIN)
                return self.child

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.child.close()
