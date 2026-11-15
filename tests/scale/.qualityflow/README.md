# Scale: QualityFlow configuration

Shared settings, the merge rules and the trust boundary are described in
[tests/.qualityflow/README.md](../../.qualityflow/README.md). This directory states only what
this team differs in.

| File | What it adds |
| --- | --- |
| `project.yaml` | This team's SIG to package mapping, and the SIG decorator its Go tests carry |
| `code_generation_config.yaml` | The package tests land in; dormant while every tier is disabled |
| `tier1.yaml` | What this team's Tier 1 scenarios are |
| `tier2.yaml` | What this team's Tier 2 scenarios are |
| `tier3.yaml` | What this team's Tier 3 scenarios are |
| `components.yaml` | The target directory entry the central map does not list |

**No tier generates for this team, and code generation is switched off rather than left to
fail.** `scale` is in `conftest.py`'s `EXCLUDE_MARKER_FROM_TIER2_MARKER`, and a test without
`@pytest.mark.scale` is stamped `tier2` by `add_tier2_marker`, so a generated density
benchmark would run in the standard tier2 lane. Nothing that reaches generated code can add
that marker, hence `enabled: false` in all three tier files. That alone would leave the
directory with no enabled language config, where `stub-generator` exits with "No enabled
language configs found"; `project.yaml` therefore sets `tier1_tests: false` and
`tier2_tests: false`, so `/generate-tests` Step 1 reports "No test generation targets
configured for this project" and stops cleanly. Those toggles do not gate `stub-generator`,
which reads no generation toggle (only `polarion`), so `/std-builder` on a target here would
still end in that error. No phase combination generates here: enabling generation would mean
changing this layer, and the missing gate is upstream. Every scale scenario stays an STP
label until a marker can reach generated code.

## Team notes

- This is the one team directory the central `component_package_map` does not list: that map
  covers the eight directories `conftest.py`'s `TEAM_MARKERS` has entries for, and `scale` is
  a test-type marker, not a team marker. `components.yaml` supplies the missing entry, as a
  stopgap that belongs in the central map.
- The `components.yaml` entry only applies to runs whose target resolves under `tests/scale/`.
  Every other run still sees no `scale` entry in the map, which is the argument for adding it
  centrally.
- No team marker is added automatically: `conftest.py` has no `scale` entry. A test in this
  directory carries `@pytest.mark.scale` itself, and `AGENTS.md` now says so - the layer's own
  README cannot, because QualityFlow never loads it.
- The decorator is `SigPerformance`, which is what kubevirt's performance tests carry. The key
  is `sig-scale`, a layer-local label; `sig-virt` is the SIG a scenario here is filed under,
  since the design-docs STPs live only under the five SIGs. Both map to `SigPerformance`.
- `tier2.yaml` and `tier3.yaml` set `reference_tests` to `null`: the directory's one module
  carries `pytest.mark.scale`, so it never collects as `tier2`, and nothing here is a Tier 3
  exemplar either.
