# Install and upgrade operators: QualityFlow configuration

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

- The `decorator_mappings` key is `sig-iuo`, the SIG this directory's scenarios carry, while
  the decorator it names is `SigOperator`, which is the one the upstream Go tests use. The
  two names genuinely differ; QualityFlow's lookup is driven by the SIG, so the key is the
  SIG and the value is the decorator.
