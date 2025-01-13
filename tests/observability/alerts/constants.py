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

SSP_DOWN = "SSPDown"
SSP_TEMPLATE_VALIDATOR_DOWN = "SSPTemplateValidatorDown"
SSP_FAILING_TO_RECONCILE = "SSPFailingToReconcile"
SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED = "SSPCommonTemplatesModificationReverted"
SSP_HIGH_RATE_REJECTED_VMS = "SSPHighRateRejectedVms"

SSP_ALERTS_LIST = [
    SSP_DOWN,
    SSP_TEMPLATE_VALIDATOR_DOWN,
    SSP_FAILING_TO_RECONCILE,
    SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED,
    SSP_HIGH_RATE_REJECTED_VMS,
]
BAD_HTTPGET_PATH = "/metrics-fake"
KUBEVIRT_VIRT_OPERATOR_READY = "kubevirt_virt_operator_ready"
