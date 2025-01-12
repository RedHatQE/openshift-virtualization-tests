from ocp_resources.resource import Resource


def get_mismatch_vendor_label(resources_list):
    failed_labels = {}
    for resource in resources_list:
        vendor_label = resource.labels[f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor"]
        if vendor_label != "redhat.com":
            failed_labels[resource.name] = vendor_label
    return failed_labels


def assert_mismatch_vendor_label(resources_list):
    failed_labels = get_mismatch_vendor_label(resources_list=resources_list)
    assert not failed_labels, f"The following resources have miss match vendor label: {failed_labels}"
