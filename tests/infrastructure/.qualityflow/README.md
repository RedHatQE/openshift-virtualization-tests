# Infrastructure: QualityFlow configuration

Shared settings, the merge rules and the trust boundary are described in
[tests/.qualityflow/README.md](../../.qualityflow/README.md). This directory states only what
this team differs in.

| File | What it adds |
| --- | --- |
| `project.yaml` | This team's SIG to package mapping |
| `code_generation_config.yaml` | The package name generated tests land in |
| `tier1.yaml` | What this team's Tier 1 scenarios are |
| `tier2.yaml` | What this team's Tier 2 scenarios are, plus a reference test |
| `tier3.yaml` | What this team's Tier 3 scenarios are, plus a reference test |

Only Tier 2 generates. Tier 1 and Tier 3 are labels an STP scenario can carry; see the shared
README for why, and for what a Tier 1 or Tier 3 scenario does at generation time.

## Team notes

- No `decorator_mappings`: no SIG decorator is recorded for this team's scenarios, so there
  is nothing to carry rather than something forgotten.
- `tier1.yaml` sets `default_package` and `reference_tests` to `null`: no Go home is recorded,
  so Tier 1 stays empty rather than pointing at another team's package.
