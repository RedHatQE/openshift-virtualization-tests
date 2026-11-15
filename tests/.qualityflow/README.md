# QualityFlow configuration for the CNV test suite

QualityFlow reads the `.qualityflow/` directory of every directory between a run's target
and the checkout root and merges them, deepest last
([qualityflow#199](https://github.com/redhat-community-ai-tools/qualityflow/pull/199)).
This directory holds what the CNV teams share; `tests/<team>/.qualityflow/` holds only what
that team differs in. It replaces the per-team fork of QualityFlow that one team needed
before, where the package name and test directory were hardcoded in the tool.

## Precedence

Three layers, lowest to highest: the central `config/projects/cnv/` in QualityFlow, this
directory, then `tests/<team>/.qualityflow/`.

A target inside one team directory gets shared-then-team settings. A target set that spans
several team directories, such as a PR's changed files, resolves to its deepest common
directory, which is `tests/`, so it gets this layer without the team deltas. Two cases get
**no layer at all**: a target set that reaches outside `tests/` (a PR touching `conftest.py`
or `utilities/` as well as a test directory resolves to the checkout root), and a single
target outside `tests/`. Those runs behave exactly as they did before these layers existed.

Everything under `tests/` inherits this layer, including directories that are not one of the
nine teams: `tests/deprecated_api/`, `tests/post_test_alerts/`,
`tests/after_cluster_deploy_sanity/`, `tests/fixtures/` and anything added later. Those
targets come out in tier mode with no `package_name_rules` of their own and no
`component_package_map` entry. Generation is not blocked there - the shared `tier2.yaml` is
enabled and supplies the language config - but a generated test would fall back to an
owning-SIG default and land outside a team directory. Treat those targets as review and
classification targets and do not run code generation on them.

## How files merge

Four rules, from QualityFlow's `config/merge.py`:

- Mappings merge recursively; the higher layer wins per key.
- Scalars replace.
- Lists replace, except lists whose items all carry an `id` (or `name`) key, which merge item
  by item; a list can also opt into `{merge: append|replace, value: [...]}`.
- `null` unsets a key: the lower layers' value is dropped and the key reads as unset.

That last one is how a team records "none" rather than "unchanged". `reference_tests: null`
says this team has no reference test; omitting the key says whatever a lower layer carries
still applies. Today no lower layer carries those keys - the central config has no
`tier*.yaml` at all - and `null` keeps it that way if the central config or this directory
ever gains one.

## What a layer may contain

A checkout is untrusted input, so a layer holds only the files listed in QualityFlow's
`config/_schema.yaml` under `config_layers`, and in each file only the keys its own
validation spec allows (`tier*.yaml` uses `validation.tier_yaml`) or that the central file
already sets. Anything else fails the run instead of being quietly ignored. Every layer needs
`project.yaml` with `version: 1` and the `project_id` it configures, and symlinks are refused.

In `project.yaml` a layer may not set `display_name`, `review_sla`, `model_policy`,
`stakeholders` or `pr_autofix`, and may not turn off the four review toggles
(`pii_sanitization`, `repo_files_fetch`, `stp_review`, `std_review`) that the central config
has enabled.

The generation toggles are not restricted anywhere, so a team layer may set them: `tests/scale/`
sets `tier1_tests` and `tier2_tests` false. This directory must not, because one line here
would stop code generation for every target under `tests/`, not only the nine team
directories. The ratchet is not the fix - it is one-way, so listing these toggles there would
reject exactly the `false` values a team layer needs. A depth-aware rule, or a central-only
list for them, is what would close it.

`display_name` in a `tier*.yaml` is a different matter: it is allowlisted there,
and the tier files in this directory set it.

A layer directory may not contain `repositories.yaml`, `jira.yaml`, `github.yaml` or
`polarion-migration/` at all; `pii_exceptions.yaml` only with a central opt-in.

`components.yaml` is allowed, and it is the one file that can add a `component_package_map`
entry. That is how `tests/scale/` gets a target directory the central map does not list.

By convention only - nothing in `config/layers.py` or `validate.py` rejects it - a team layer
is the only place a `components.yaml` belongs: one here would add map entries for every target
under `tests/`, redirecting other teams' generated code, and review is what has to refuse it.
The same convention covers `templates/**` and `reference/**`, which are copied whole over the
central project directory, and `patterns/*.yaml`, which deep-merges. This directory holds only
settings in the shape of `project.yaml`, `code_generation_config.yaml` and `tier*.yaml`.

QualityFlow does not validate a layer's `package_path` at all - a `../../` or absolute value
passes every check - so a team's `package_path` must stay inside that team's own directory, by
review rather than by tooling.

## The three tiers

| Tier | `enabled` | Generates |
| --- | --- | --- |
| Tier 1 | `false` | no |
| Tier 2 | `true` | yes |
| Tier 3 | `false` | no |

Tier 1 is Go/Ginkgo in `kubevirt/kubevirt`, and a Go generation target would resolve to
this Python checkout.

Tier 3 tests do belong in this repository and carry `@pytest.mark.tier3` by hand, but nothing
a layer can set makes a *generated* test carry that marker: `tier*.yaml` `markers` has no
consumer, and `stub_marks` marks the docstring-only stub, which `/generate-tests` leaves off
the implemented test. An unmarked test is stamped `tier2` by `conftest.py`, so a generated
Tier 3 test would run in the tier2 lane.

`tests/scale/` sets all three tiers to `false` for the same reason - a generated test there
needs `@pytest.mark.scale` to stay out of the tier2 lane - and sets `tier1_tests: false` and
`tier2_tests: false`, so `/generate-tests` Step 1 reports "No test generation targets
configured for this project" and stops. Those toggles do not reach `stub-generator`, which
reads no generation toggle (only `polarion`): a run that resolved its `config_dir` here through
`/std-builder` would still end in "No enabled language configs found". No combination of
phases generates here: `/generate-tests` stops on the toggles and `/std-builder` stops inside
`stub-generator`, so enabling generation would mean changing this layer.

`tier-classifier` is handed every `tier*.yaml` to build the list of available tiers, not only
the enabled ones, which is what keeps `[Tier 1]` and `[Tier 3]` valid labels on an STP
scenario for these directories. That is how the skill describes its input, not a guarantee
written down in the caller. If it ever changes, the consequence is not that the labels vanish
and the files can go: Tier 1 and Tier 3 scenarios would be classified Tier 2 - single-feature
ones directly, cost-heavy ones through the classifier's own Tier 2 promotion triggers - and
then generate into the tier2 lane, which is the outcome the tier files exist to prevent. The
remedy would be upstream, not deleting the files.

The consequence is deliberate and worth stating plainly: **a Tier 1 or Tier 3 scenario
produces no stub and no test here.** `stub-generator` reports `N scenarios have no matching
language config (tier: ...)` and drops them. That warning is expected output for these
directories, not a defect to chase.

## Checking a change

```bash
# from a QualityFlow checkout that carries config/projects/cnv/
uv run python config/validate.py --repo /path/to/openshift-virtualization-tests
```

`--repo` checks each layer on its own: the identity marker, the file and key allowlists, the
toggle ratchet. It does not validate a merged result. Merging is the tail of
`layers.resolve()`, which only real runs go through, so per-layer passes are necessary but
not sufficient.

Against a plain clone of the public QualityFlow repository it prints
`(project 'cnv' is not in .../config/projects: checked against the schema only)`: the key
allowlist is then checked against the schema alone, without the union with the central files,
and the ratchet runs against `_defaults.yaml` rather than the central project's toggles.
`validate_repo()` also passes `project_id=None`, so a layer declaring the wrong `project_id`
is not reported by it, though a run skips that layer. Run it from a checkout that carries the
central config.

To see which layers a target picks up, resolve it directly. This prints `tests/storage` then
`tests` for a single-team target, and only `tests` when the target set spans two team
directories:

```python
import os, sys; sys.path.insert(0, "config")
import layers, validate
repo = "/path/to/openshift-virtualization-tests"
repos = validate.load_yaml("config/projects/cnv/repositories.yaml")
schema = validate.load_yaml("config/_schema.yaml")
targets = ["primary_repo:tests/storage/test_probe.py"]
found = layers.discover(repos, targets, {**os.environ, "SOURCE_REPO_PATH": repo},
                        schema["config_layers"]["default_order"])
print([d.relative_to(repo) for _, _, _, d in found])
```

## Known limitations

- A generated Tier 2 test must not repeat the team or `tier2` marker: `conftest.py` adds both
  from the test's directory. `tests/scale/` is the exception, and a scale test must carry
  `@pytest.mark.scale` itself, exactly as `test_scale_benchmark.py` does. `AGENTS.md` records
  that, because a layer README is never loaded by QualityFlow.
- `tier1.yaml` is still read by `review-rules-extractor`, which takes the standard frameworks
  from every `tier*.yaml` without looking at `enabled`. The Go framework and Ginkgo stub
  conventions therefore appear in the review rules for these directories even though no Go is
  generated. Removing the file would remove the `[Tier 1]` label, so it stays and the leak is
  recorded here.
- `assertion_library` is read by `std-generator` in tier mode but is not a key a layer may
  set, so a generated Python test declares its assertions through `test_patterns` instead.
  That is an upstream allowlist gap, not something a layer can fix.
- `OWNERS` cannot live in this directory: it is not an allowed layer file, and the run
  refuses a layer holding one. A change here therefore falls to the repository root
  approvers, and one edit reconfigures all nine teams at once. A `tests/OWNERS` would reach
  every directory under `tests/`, not only the nine teams.
- QualityFlow does not validate a layer's `package_path`. It also lets `feature_toggles: null`
  through - any other non-mapping is rejected as "feature_toggles must be a mapping" - and
  `merge()` then drops the central toggles entirely, including any the central project sets to
  a non-default value such as `polarion_lint`. Neither is reachable from this change
  set, and neither can be fixed from a layer.

## Adding a team

Create `tests/<team>/.qualityflow/` with:

- `project.yaml`: `version: 1`, `project_id: "cnv"`, `sig_mappings` (SIG to package, for
  readers - nothing consumes it), and, when the team's upstream Go tests carry a SIG
  decorator, `decorator_mappings` keyed by the SIG the team's STP scenarios carry, not by the
  decorator's own name.
- `code_generation_config.yaml`: `package_name_rules`, which is what routes generated tests
  into the team's directory.
- `tier1.yaml`, `tier2.yaml`, `tier3.yaml`: that team's `description`, plus `reference_tests`
  (or `reference_tests: null`), plus `default_package` in `tier1.yaml` when a Go home exists.
- `components.yaml`: only when the directory is not already in the central
  `component_package_map`. `tests/scale/.qualityflow/` is the worked example.

Two changes outside the layer are also needed, and neither is automatic:

- an entry in `conftest.py`'s `TEAM_MARKERS`, or the team marker is never added and every CI
  lane selecting by that marker skips the new tests. This is a repo-wide collection change;
  `tests/scale/` is the case where it was not done, and its consequences are recorded there.
- the team directory's own `OWNERS` file.

Everything else comes from this directory.
