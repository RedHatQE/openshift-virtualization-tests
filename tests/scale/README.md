# scale testing

#### This is a guide for scale test - running a high number of VMs

    - Create the necessary DV for the VMs
    - Create the VMs according to the yaml file
    - Over the given test duration, iterate every 10 minutes over all the created VMs to see all in running state
    - Print cluster statistics

    The test will print out the VMs distribution across the nodes and the nodes statistics.
    If the test passes it will delete the resources (namespace, VMs, DVs), unless configured otherwise in the configuration yaml.
    If the test fails the resources will be kept and must-gather data will be collected.

### Jenkins run

    You can run the test using Jenkins at - https://main-jenkins-csb-cnvqe.apps.ocp-c1.prod.psi.redhat.com/job/scale-test
    The job will update the default scale_params.yaml file located at openshift-virtualization-tests/tests/scale/scale_params.yaml, according to the values entered in the test.

### Manual run

    In order to run the test manually without the jenkins job:
    - make the required changes in the yaml param file, you can optionally enter the path to the chosen file using --scale-params-file,
    the default file in case you need an example is found at openshift-virtualization-tests/tests/scale/scale_params.yaml
    - run the test using pytest (uv run pytest -m scale -o log_cli=true -s)

### Test parameter

    "vms" - defines the amount of VMs to run, and the configruation.

    "memory" and "cores" -  taken by refenece from ("linux_vms_cores", "windows_vms_cores") or can be explicitly overwritten:
    "memory": effect vm definition resources.requests.memory"
    "cores": effect vm defintion cpu.cores

    "keep_resources" - can be set to True in order to keep or False to delete the resources at the
    end of the test regerdless of the result.
    "run_live_migration" - can be set to True in order to run test_mass_vm_live_migration for all the VMs
    "test_namespace" - the name of the project the test resources will be created at.

    "test_duration" - number of minutes for the test to keep running
    "vms_verification_interval" - minutes to wait between each verification that all VMIs are in ready state

### Notes

- The test takes the latest OS as configured in openshift-virtualization-tests.
- You can use a different params file using the --scale-params-file option, the jenkins job will **not** update this file.
- In order to add new storage types for the test, you should add the storage type to SCALE*STORAGE_TYPES const in test_scale_benchmark.py, and
  num*<storage_type>\_vms to scale_params.yaml
