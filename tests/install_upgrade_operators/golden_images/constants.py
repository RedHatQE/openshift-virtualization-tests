from tests.install_upgrade_operators.constants import CUSTOM_DATASOURCE_NAME
from utilities.constants import OUTDATED, WILDCARD_CRON_EXPRESSION

HCO_CR_DATA_IMPORT_SCHEDULE_KEY = "dataImportSchedule"
RE_NAMED_GROUP_MINUTES = "minutes"
RE_NAMED_GROUP_HOURS = "hours"
DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX = (
    rf"(?P<{RE_NAMED_GROUP_MINUTES}>\d+)\s+" rf"(?P<{RE_NAMED_GROUP_HOURS}>\d+)\/12\s+\*\s+\*\s+\*\s*$"
)
COMMON_TEMPLATE = "commonTemplate"
CUSTOM_TEMPLATE = "customTemplate"
CUSTOM_CRON_TEMPLATE = {
    "metadata": {
        "annotations": {
            "cdi.kubevirt.io/storage.bind.immediate.requested": "false",
        },
        "name": "custom-test-cron",
    },
    "spec": {
        "garbageCollect": OUTDATED,
        "managedDataSource": CUSTOM_DATASOURCE_NAME,
        "schedule": WILDCARD_CRON_EXPRESSION,
        "template": {
            "metadata": {},
            "spec": {
                "source": {
                    "registry": {
                        "imageStream": "custom-test-guest",
                        "pullMethod": "node",
                    },
                },
                "storage": {
                    "resources": {
                        "requests": {
                            "storage": "7Gi",
                        }
                    }
                },
            },
        },
    },
}
