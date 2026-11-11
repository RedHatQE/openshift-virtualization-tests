SSP_HIGH_RATE_REJECTED_VMS = "SSPHighRateRejectedVms"
SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED = "SSPCommonTemplatesModificationReverted"
KUBEVIRT_VMI_NUMBER_OF_OUTDATED = "kubevirt_vmi_number_of_outdated"
VIRT_ALERTS_LIST = [
    # virt-operator
    "VirtOperatorDown",
    "NoReadyVirtOperator",
    "LowReadyVirtOperatorsCount",
    "LowVirtOperatorCount",
    "NoLeadingVirtOperator",
    "VirtOperatorRESTErrorsBurst",
    "VirtOperatorRESTErrorsHigh",
    # virt-api
    "VirtAPIDown",
    "NoReadyVirtAPI",
    "LowReadyVirtAPICount",
    "LowVirtAPICount",
    "VirtApiRESTErrorsBurst",
    "VirtApiRESTErrorsHigh",
    # virt-controller
    "VirtControllerDown",
    "NoReadyVirtController",
    "LowReadyVirtControllersCount",
    "LowVirtControllersCount",
    "VirtControllerRESTErrorsBurst",
    "VirtControllerRESTErrorsHigh",
    # virt-handler
    "VirtHandlerDown",
    "NoReadyVirtHandler",
    "LowReadyVirtHandlerCount",
    "VirtHandlerDaemonSetRolloutFailing",
    "VirtHandlerRESTErrorsBurst",
    "VirtHandlerRESTErrorsHigh",
]
SSP_ALERTS_LIST = [
    "SSPDown",
    "SSPTemplateValidatorDown",
    "SSPFailingToReconcile",
    "SSPCommonTemplatesModificationReverted",
    SSP_HIGH_RATE_REJECTED_VMS,
]
