KUBEVIRT_VIRT_OPERATOR_READY = "kubevirt_virt_operator_ready"
SSP_HIGH_RATE_REJECTED_VMS = "SSPHighRateRejectedVms"
BAD_HTTPGET_PATH = "/metrics-fake"
SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED = "SSPCommonTemplatesModificationReverted"
VIRT_ALERTS_LIST = [
    "VirtOperatorDown",
    "NoReadyVirtOperator",
    "LowVirtOperatorCount",
    "VirtAPIDown",
    "LowVirtOperatorCount",
    "VirtHandlerDaemonSetRolloutFailing",
    "LowReadyVirtOperatorsCount",
    "NoLeadingVirtOperator",
    "VirtOperatorRESTErrorsBurst",
    "VirtOperatorRESTErrorsHigh",
    "VirtApiRESTErrorsBurst",
    "VirtApiRESTErrorsHigh",
    "LowReadyVirtControllersCount",
    "NoReadyVirtController",
    "VirtControllerRESTErrorsHigh",
    "VirtControllerRESTErrorsBurst",
    "VirtHandlerRESTErrorsHigh",
    "VirtHandlerRESTErrorsBurst",
]
SSP_ALERTS_LIST = [
    "SSPDown",
    "SSPTemplateValidatorDown",
    "SSPFailingToReconcile",
    "SSPCommonTemplatesModificationReverted",
    SSP_HIGH_RATE_REJECTED_VMS,
]
