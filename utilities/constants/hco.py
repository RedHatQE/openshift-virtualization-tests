"""HyperConverged Operator (HCO) configuration constants.

Covers expected status conditions, upgrade stream identifiers, TLS security profile keys,
feature gate key names, and the full CNV CRD list.

Not here:
- HCO-managed component deployment/pod name strings → ``components.py``
"""

from ocp_resources.aaq import AAQ
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource
from ocp_resources.ssp import SSP

DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
DEFAULT_KUBEVIRT_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.CREATED: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
DEFAULT_RESOURCE_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
EXPECTED_STATUS_CONDITIONS = {
    HyperConverged: DEFAULT_HCO_CONDITIONS,
    KubeVirt: DEFAULT_KUBEVIRT_CONDITIONS,
    CDI: DEFAULT_RESOURCE_CONDITIONS,
    SSP: DEFAULT_RESOURCE_CONDITIONS,
    NetworkAddonsConfig: DEFAULT_RESOURCE_CONDITIONS,
    AAQ: DEFAULT_RESOURCE_CONDITIONS,
}


class UpgradeStreams:
    X_STREAM = "x-stream"
    Y_STREAM = "y-stream"
    Z_STREAM = "z-stream"


TLS_OLD_POLICY = "old"
TLS_CUSTOM_POLICY = "custom"
TLS_SECURITY_PROFILE = "tlsSecurityProfile"
HOTFIX_STR = "hotfix"
PRODUCTION_CATALOG_SOURCE = "redhat-operators"
ENABLE_COMMON_BOOT_IMAGE_IMPORT = "enableCommonBootImageImport"
RESOURCE_REQUIREMENTS_KEY_HCO_CR = "resourceRequirements"
FEATURE_GATES = "featureGates"
HCO_SUBSCRIPTION = "hco-operatorhub"
IMAGE_CRON_STR = "image-cron"
HCO_DEFAULT_CPU_MODEL_KEY = "defaultCPUModel"

DATA_SOURCE_NAME = "DATA_SOURCE_NAME"
DATA_SOURCE_NAMESPACE = "DATA_SOURCE_NAMESPACE"
SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME = "dataImportCronTemplates"
COMMON_TEMPLATES_KEY_NAME = "commonTemplates"

DATA_IMPORT_CRON_ENABLE = (
    f"metadata->annotations->{DataImportCron.ApiGroup.DATA_IMPORT_CRON_TEMPLATE_KUBEVIRT_IO}/enable"
)

VM_CRD = f"virtualmachines.{Resource.ApiGroup.KUBEVIRT_IO}"
VM_CLONE_CRD = f"virtualmachineclones.clone.{Resource.ApiGroup.KUBEVIRT_IO}"
VM_EXPORT_CRD = f"virtualmachineexports.export.{Resource.ApiGroup.KUBEVIRT_IO}"
ALL_CNV_CRDS = [
    f"aaqs.{Resource.ApiGroup.AAQ_KUBEVIRT_IO}",
    f"cdiconfigs.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"cdis.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"dataimportcrons.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datasources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datavolumes.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"hostpathprovisioners.{Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO}",
    f"hyperconvergeds.{Resource.ApiGroup.HCO_KUBEVIRT_IO}",
    f"kubevirts.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"migcontrollers.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"migrationpolicies.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"networkaddonsconfigs.{Resource.ApiGroup.NETWORKADDONSOPERATOR_NETWORK_KUBEVIRT_IO}",
    f"objecttransfers.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"ssps.{Resource.ApiGroup.SSP_KUBEVIRT_IO}",
    f"storageprofiles.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"virtualmachinebackups.backup.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachinebackuptrackers.backup.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineclusterinstancetypes.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"virtualmachineinstancetypes.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"virtualmachineinstancemigrations.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancepresets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancereplicasets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstances.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachinepools.{Resource.ApiGroup.POOL_KUBEVIRT_IO}",
    f"virtualmachinerestores.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    VM_CRD,
    f"virtualmachinesnapshotcontents.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    f"virtualmachinesnapshots.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    VM_CLONE_CRD,
    f"virtualmachineclusterpreferences.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    VM_EXPORT_CRD,
    f"virtualmachinepreferences.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"volumeuploadsources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"volumeimportsources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"volumeclonesources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"openstackvolumepopulators.forklift.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"ovirtvolumepopulators.forklift.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"multinamespacevirtualmachinestoragemigrationplans.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"multinamespacevirtualmachinestoragemigrations.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"virtualmachinestoragemigrationplans.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"virtualmachinestoragemigrations.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
]
