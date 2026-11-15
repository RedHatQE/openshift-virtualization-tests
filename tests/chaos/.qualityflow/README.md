# Chaos: QualityFlow configuration

Shared settings, the merge rules and the trust boundary are described in
[tests/.qualityflow/README.md](../../.qualityflow/README.md). This directory states only what
this team differs in.

| File | What it adds |
| --- | --- |
| `project.yaml` | This team's SIG to package mapping |
| `code_generation_config.yaml` | The package name generated tests land in |
| `tier1.yaml` | What this team's Tier 1 scenarios are |
| `tier2.yaml` | What this team's Tier 2 scenarios are |
| `tier3.yaml` | What this team's Tier 3 scenarios are, plus a reference test |

Only Tier 2 generates. Tier 1 and Tier 3 are labels an STP scenario can carry; see the shared
README for why, and for what a Tier 1 or Tier 3 scenario does at generation time.

## Team notes

- No `decorator_mappings`: the team's Tier 1 tests have no SIG decorator recorded upstream,
  so there is nothing to carry rather than something forgotten.
- The design-docs STPs live only under sig-infra, sig-iuo, sig-network, sig-storage and
  sig-virt, so a scenario from this team is filed under `sig-virt`. `sig-chaos` is kept as
  a layer-local label. Both map to the `chaos` package.
- `tier1.yaml` sets `default_package` and `reference_tests` to `null`: kubevirt has no chaos
  test package, so this team has no Go home to point Tier 1 at.
- `tier2.yaml` sets `reference_tests` to `null`: every chaos test carries `pytest.mark.chaos`,
  which `conftest.py` lists in `EXCLUDE_MARKER_FROM_TIER2_MARKER`, so no chaos module ever
  collects as `tier2` and none is an exemplar for it.
