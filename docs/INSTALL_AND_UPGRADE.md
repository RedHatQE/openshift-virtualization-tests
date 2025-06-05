## Install openshift-virtualization tests

Installation tests allow us to use either the `production` or `osbs` catalogsource for deployment.

Note:
1. Install test expects no cnv installation exists on the cluster. Installation of openshift-virtualization x.y._ is only supported on ocp x.y._
2. CNV_VERSION_EXPLORER_URL environment variable expected to be set up for local runs. URL information can be found in Confluence.

##### Install from production catalogsource

In this case, installation of openshift virtualization would take place using redhat-operator catalogsource.

```bash
pytest tests/install_upgrade_operators/product_install/test_install_openshift_virtualization.py --install --cnv-source production
```

##### Install from osbs catalogsource

In this case, installation would take place using a custom catalogsource using specified IIB image. Currently only installation using brew url is supported.

```bash
pytest tests/install_upgrade_operators/product_install/test_install_openshift_virtualization.py --install --cnv-source osbs --cnv-image brew.registry.redhat.io/rh-osbs/iib:<image>
```

## Upgrade tests

Current upgrade test automation allows us to run just the ocp/cnv/eus upgrade.
As default, the upgrade will run with pre- and post-upgrade validation of various components.

Note:
1. Before running upgrade tests, please check "Cluster requirements" section to see minimum requirements in terms of cluster size.
2. CNV_VERSION_EXPLORER_URL environment variable expected to be set up for local runs. URL information can be found in Confluence.

##### Y-stream Upgrade

In this case, upgrade testing would always involve upgrading both ocp and cnv.
Please note, in Y-1 -> Y upgrade, OCP must be upgraded first, followed by CNV upgrades. (e.g. upgrading from 4.Y latest z stream -> 4.Y+1.0, ocp must be upgraded to 4.Y+1 first, before cnv can be upgraded).

##### Z-stream Upgrade

Here, no ocp upgrade is needed (e.g. 4.Y.z-1 -> 4.Y.z).

##### EUS Upgrade:
EUS-to-EUS updates are only viable between even-numbered minor versions of OpenShift Container Platform. (e.g 4.Y.z -> 4.Y+2.z)


#### OCP upgrade

Command to run entire upgrade test suite for ocp upgrade, including pre and post upgrade validation:

```bash
--upgrade ocp --ocp-image <ocp_image_to_upgrade_to>
```

Command to run only ocp upgrade test, without any pre/post validation:

```bash
-m product_upgrade_test --upgrade ocp --ocp-image <ocp_image_to_upgrade_to>
```

To upgrade to ocp version: 4.18.15, using <https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com/releasestream/4-stable/release/4.18.15>, following command can be used:

```bash
--upgrade ocp --ocp-image quay.io/openshift-release-dev/ocp-release:4.18.15-x86_64
```

Note: OCP images information can be found at: <https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com/>.

Currently, automation supports ocp upgrades using stable, ci, nightly and rc images for ocp

#### CNV upgrade
Parameters:

| Parameter Name  |      Requirement      |  Default Value  |       Possible Value       |
|:----------------|:---------------------:|:---------------:|:--------------------------:|
| `--cnv-version` |     **Required**      |        -        |           4.Y.z            |
| `--cnv-image`   |     **Required**      |        -        |        -image path-        |
| `--cnv-source`  |     **Optional**      |      osbs       |   osbs, fbc, production    |
| `--cnv-channel` |     **Optional**      |     stable      | stable, candidate, nightly |

Command to run entire upgrade test suite for cnv upgrade, including pre and post upgrade validation:

```bash
--upgrade cnv --cnv-version <target_version> --cnv-image <cnv_image_to_upgrade_to>
```

Command to run only cnv upgrade test, without any pre/post validation:

```bash
-m cnv_upgrade --upgrade cnv --cnv-version <target_version> --cnv-image <cnv_image_to_upgrade_to>
```

To upgrade to cnv 4.Y.z, using the cnv image that has been shipped, following command could be used:
```bash
--upgrade cnv --cnv-version 4.Y.z --cnv-image <cnv_image_to_upgrade_to>
```

#### EUS upgrade
You must provide --eus-ocp-images via cli, which is two comma separated ocp images for EUS upgrade.
The default target cnv version will be 4.Y+2.0. Optionally, --eus-csv-target-version can be provided for 4.Y+2.z version.
Command to run entire upgrade test suite for EUS upgrade, including pre and post upgrade validation:

```bash
--upgrade eus --eus-ocp-images <ocp_image_version_4.y+1.z>,<ocp_image_version_4.y+2.z> --eus-cnv-target-version <4.Y+2.z|None>
```
#### Custom upgrade lanes

The argument `--upgrade_custom` can be used instead of `--upgrade` to run custom upgrade lanes with non-default configurations (e.g., with customized HCO feature gates).

Note: custom upgrades should not be combined, to exclude unnecessary components `--ignore` argument can be used (e.g. `--ignore=tests/compute/upgrade_custom/swap/`)


## Network tests
Upgrade tests must be run against a large deployment(24GiB RAM, 250GB volume size)
Upgrade network tests can't be run against a non-multi-nic cluster. To run upgrade against
such clusters, we must ignore the network component.

```bash
--ignore=tests/network/
```
