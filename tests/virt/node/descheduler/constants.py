DESCHEDULER_SOFT_TAINT_KEY = "nodeutilization.descheduler.openshift.io"

# stress-ng workloads started inside guests to overload a single node.
# CPU: one worker per online CPU.
STRESS_NG_CPU_LOAD_COMMAND = "nohup stress-ng --cpu 0 &> /dev/null &"
# Memory: allocate and hold most of the guest memory resident with negligible CPU
# (touch once via a single worker, then keep the mapping and sleep instead of re-writing).
STRESS_NG_MEMORY_LOAD_COMMAND = (
    "nohup stress-ng --vm 1 --vm-bytes 90% --vm-keep --vm-hang 3600 --timeout 0 &> /dev/null &"
)
