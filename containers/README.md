# Containers and image artifacts

- **fedora/** – Build the **customized** Fedora container-disk image (sysprepped qcow2 in a container). See [fedora/README.md](fedora/README.md). The resulting qcow2 can be published to Artifactory as the main test image for that arch.

- **fedora_artifacts/** – Build **base** Fedora disk artifacts (qcow2, raw, .gz, .xz) for a given version. Output goes to `fedora_artifacts/out/` for upload to Artifactory. Optionally copy the customized qcow2 from `fedora/` into `out/` so all artifacts are in one place. See [fedora_artifacts/README.md](fedora_artifacts/README.md).

- **internal_http/** – Build the internal HTTP server container image used by storage/CDI tests. See team Confluence for build instructions.

- **utility/** – Utility container image. See [utility/README.md](utility/README.md).
