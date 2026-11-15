# Virtualization: QualityFlow configuration

Shared settings, the merge rules and the trust boundary are described in
[tests/.qualityflow/README.md](../../.qualityflow/README.md). This directory states only what
this team differs in.

| File | What it adds |
| --- | --- |
| `project.yaml` | This team's SIG to package mapping, and the SIG decorator its Go tests carry |
| `code_generation_config.yaml` | The package name generated tests land in |
| `tier1.yaml` | What this team's Tier 1 scenarios are, plus its Go home |
| `tier2.yaml` | What this team's Tier 2 scenarios are, plus a reference test |
| `tier3.yaml` | What this team's Tier 3 scenarios are, plus a reference test |

Only Tier 2 generates. Tier 1 and Tier 3 are labels an STP scenario can carry; see the shared
README for why, and for what a Tier 1 or Tier 3 scenario does at generation time.

## Team notes

- The decorator is `SigCompute`, because kubevirt's virtualization tests carry that SIG even
  though the CNV feature area is `sig-virt`. The key stays `sig-virt`: it is the SIG this
  directory's scenarios carry, and QualityFlow looks the decorator up by that SIG.
