global config


hco_cr_name = "kubevirt-hyperconverged"
cnv_namespace = "openshift-cnv"
hco_subscription = "hco-operatorhub"

for _dir in dir():
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
