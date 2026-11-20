# Network Tests — AGENTS.md

Scope: `tests/network/` (sig-network). The repo-wide root [`AGENTS.md`](../../AGENTS.md) and all
pre-commit hooks apply **in full**. This file only **adds or sharpens** rules for network code —
it does not restate inherited root rules and never relaxes a mandatory one. The few places where a
network rule *differs from* or *sharpens* root are marked inline *(delta: …)* and indexed in
[§10](#10-network-deltas-from-root). When a rule is challenged, cite the supporting code or review
link.

---

## 1. Network domain terminology & correctness

Use the vocabulary, shorthand table (localnet / Linux bridge / UDN / pod network / SR-IOV), and
VLAN ranges in [`tests/network/README.md`](README.md) — link it, don't copy it into tests. A VM
interface has two independent layers: CNI (pod plugin) and KubeVirt network binding.

Network correctness gotchas (not in the README):

- **MTU** is configured on ports/interfaces via the documented MTU field of the selected
  API/plugin/version. Distinguish the Linux-bridge *device* MTU, attached-*interface* MTUs, and
  OVS configuration — name the technology explicitly. Jumbo-frame tests must additionally establish
  support across the real forwarding path (including the inter-node path when exercised).
- **IPAM is plugin-specific:** within the `ipam` block only `type` is universal; every other IPAM
  field depends on the plugin. (CNI separately defines top-level metadata such as `name` /
  `cniVersion`.) Don't assume identical `ipam` schemas across plugins.
- NNCP has no `FAILING` condition type. A "secondary network VM" usually still has its primary
  network wired.

---

## 2. Code placement & reuse

**Search before writing. Reuse before adding. Never leave a duplicate behind.** Placement, from
most local to most shared:

1. **Feature-local** — `tests/network/<feature>/lib<feature>.py` (helpers) + `conftest.py`
   (fixtures). Use `lib<feature>.py` for new features or newly extracted helpers; do not rename an
   existing `utils.py` unless you are refactoring that suite entirely. *(delta: root prescribes
   `<feature_dir>/utils.py`; `lib<feature>.py` — a concise domain name, not the whole path — is the
   network convention, to be reconciled with root on adoption.)*
2. **Network-shared** — `tests/network/libs/` for helpers/wrappers reused across network features
   (e.g. `vm_factory.py`, `connectivity.py`, `cluster_user_defined_network.py`, `bgp.py`,
   `localnet.py`).
3. **Repo-wide primitives** — top-level `libs/net`, `libs/vm`, `libs/infra` (strictly typed, used
   beyond network).

- **Importing from another test suite is a red flag** — if a helper is reused across suites it
  belongs in `libs/`, not imported sideways (e.g. from `localnet.liblocalnet`).
- Prefer `libs/` over `utilities/` for new shared network code. *(delta: root routes shared code to
  `utilities/`; it also acknowledges `tests/<team>/libs/`.)*
- **Don't re-implement what the `ocp-resources` wrapper already provides** — e.g. use
  `vm.vmi.wait_for_condition(condition="AgentConnected", ...)`, not a new `wait_for_guest_agent`.
  Stable, logic-free helpers belong *in* the wrapper.
- **VM builders — discovery then placement.** Builders live in local `lib<feature>.py` files and
  fixtures as well as the shared factories. Before writing one, search local helpers, fixture
  construction paths, shared domain helpers (`tests/network/libs/localnet.py`, `vm_factory.py`),
  and `libs/vm/factory.py` — search by *what it does*, not just by name. Promote a builder to the
  appropriate common domain module only when **more than one suite** consumes it; a genuinely
  feature-local builder with only local consumers stays local. Never import a builder sideways from
  another suite's helper.
- **When extracting to a shared location, delete the original copy** — leaving one behind defeats
  deduplication.
- **Reuse shared implementations and extract repeated domain logic.** Repeated trivial construction
  or delegation syntax alone does not require inheritance or a new abstraction; **neither copy
  count nor line count** determines whether code contains domain logic. Preserve return values
  required by resource contracts or other consumers.
- **Keep resource-specific metadata with its resource or factory.** Pass an existing resource when
  the operation needs its identity, client, metadata, or behavior; accept a name, address, or
  selector directly when that is the operation's actual input. Don't export an unscoped constant
  (e.g. a Kubernetes label mapping) that a resource or its factory should own, and don't
  reconstruct an available resource merely to recover context the caller already has.
- **Resource clients:** follow root's resource-client and absence-contract rules (explicit
  `client=`, reuse the client already in the call path, installed `ocp_resources` classes only).
  Local `Resource`/`NamespacedResource` subclasses are legacy — do not model new code on them. A
  CRD spec modeled as a dataclass (see §3) is not a license to add a new local Resource subclass.

---

## 3. Library & helper design

- **Split flags that make one helper perform unrelated workflows.** Typed arguments that configure
  one coherent operation are valid; a plain `if` or a Boolean argument is not itself a defect.
  Inspect which responsibilities a flag selects and its maintenance cost. Example: selecting an
  address family configures one connectivity check (fine); creating a VM and *optionally migrating
  it* adds a separate lifecycle action (split it).
- **Encapsulate — hide incidental plumbing** (the traffic tool, raw backend, internal attributes)
  behind a tool-agnostic API, so the backend can change without touching callers. Attributes
  private by default; expose only what callers need.
- **Expose the typed controls that *define* the experiment** — `ip_family`, `expect_connectivity`,
  interface binding, TCP segment size, and the port *when the scenario concerns port selection,
  reachability, or port-based policy*.
- **Minimalism / YAGNI.** Ship only what the task needs; drop unused params/attributes/options.
- **Explicit, typed arguments.** No "no-limit" `**kwargs` APIs; no fake defaults the caller should
  state; don't add a parameter already derivable from another argument.
- **`dataclass` holds data only — no methods.** Model CRD specs as dataclasses serialized via
  `asdict(..., dict_factory=dict_normalization_for_dataclass)` — see
  `tests/network/libs/cluster_user_defined_network.py`. Prefer **composition over inheritance**:
  repeated trivial construction or delegation alone does not justify a new abstraction — reuse
  shared domain logic. ("If you cannot find a good name for a base class, it is not a fit.")
- **No inner/nested functions without a closure need** — make them module-level
  `_private_function` (testable, and avoids closure-variable leaks).
- **Type hints must be correct, not just linter-quiet** — the declared return type must match what
  the body returns; self-referencing returns use the string form (`-> "TrafficGenerator"`).

---

## 4. Waiting, polling & connectivity

- **Prefer the `@retry` decorator over a hand-written `TimeoutSampler` loop** — both come from
  `timeout_sampler`; `@retry` keeps the wait policy at the definition and the call site clean.
  *(delta: root shows the `for sample in TimeoutSampler(...)` loop — same package, different form.)*
- **Never use `time.sleep()`.** Justify every timeout value — padded waits hide real failures (a
  TCP handshake is sub-second).
- **No races / no check-then-act** — wait for the expected state rather than asserting right after
  an async action; prefer EAFP.
- **Context managers must be leak-safe** — failing to *enter* a context does not call its *exit*; a
  started server must be torn down even if the client fails. Decorate generators with
  `@contextmanager`.

### Connectivity (test-design guidance)

Choose observations from the **STP's claimed behavior**, and exercise the *intended* path so
success cannot come from an unintended interface, route, or same-node bypass (see the ECMP /
`bind_dev` rationale in `tests/network/libs/connectivity.py`):

- **Distinguish the objectives** — intended-path reachability, *new* TCP establishment, *preserved*
  TCP session (same connection carries continued data exchange across the disruption), and
  interruption/gap measurement. Never label a new connection "preserved".
- **TCP and ICMP are different check types and may coexist.** There is no universal TCP preference:
  a stateful TCP session is right when the claim is session survival or data exchange, while
  continuous ICMP is the right tool to measure a connectivity gap (see
  `tests/network/localnet/migration_stuntime/`).
- Don't assert fragile generated-config *text*; keep the semantic route/isolation observations the
  STP actually requires. For EVPN/BGP, working connectivity over the intended path is the assertion.
- Reuse `poll_tcp_connectivity` / `client_server_active_connection`; don't build
  EndpointSlice/Service scaffolding when two VMs suffice (those resources are fine when they are
  what's under test).
- Note: `poll_tcp_connectivity` is **success-or-raise** (`@retry` returns a truthy result or raises
  `TimeoutExpiredError`), so an unasserted call still fails the test. Assert any *plain* boolean
  predicate that can legitimately return `False`, and prefer an explicit, clearly-named step so a
  reader sees what is verified.

(Detailed helper contracts and protocol-selection examples belong in supporting docs, not here.)

---

## 5. Fixtures

**Avoid pass-through fixtures.** A pass-through fixture only forwards an existing fixture or an
attribute reachable from it and adds no meaningful fixture semantics (e.g. a fixture that just
returns `clusterip_service.instance.spec.clusterIP` — use it directly instead).

Retain fixtures that provide real value: setup, teardown, parametrized inputs, an intentional
lifetime/isolation boundary, or dependency tracking. Resource creation is not the only legitimate
purpose — the NMState tracker (`nmstate_dependent_placeholder`, `tests/fixtures/network/nmstate.py`)
is a valid tracking fixture that creates nothing.

- **Scope, placement, and execution order are distinct:** choose scope from reuse/isolation needs,
  placement from visibility/ownership; order parameters per root, and encode required *execution*
  order through fixture dependencies, not signature position.
- **Prerequisite checks** use explicit dependencies or `usefixtures` and **raise a descriptive
  exception** on failure (not `assert`; see §8). Do not add autouse fixtures for this; an existing
  suite-wide autouse fixture does not justify creating more.

---

## 6. Test design

- **One test tells one story.** Intermediate `assert`s are *steps* in that story, not separate
  tests. Do setup and actions, then verify; establishing and confirming a baseline (e.g. an active
  session before disruption) is *setup*, not interleaving.
- **The core assertion must verify the real behavior**, and nothing silently passes — missing or
  broken config fails loudly, and a reader can see *what* is asserted.
- **Tests are independent** — avoid `@pytest.mark.dependency` / ordering; use shared fixtures for
  resource dependencies. For a genuine cross-test side-effect, prefer `@pytest.mark.incremental`
  (with a *why* comment).
- **Parametrize over duplicated/conditional tests** — `@pytest.mark.parametrize("ip_family", ...)`;
  use *one* test ID across IP families, not one per family.
- **Dual-stack / IPv6:** know the product reality (e.g. EVPN VTEPs are IPv4-only); when IPv6 is
  skipped, track the gap with a backlog ticket.
- **Align test verdicts with the STD `Expected:` results** — don't invent unrelated verifications,
  and don't turn setup/precondition verifications into additional test verdicts (preconditions are
  established in fixtures).

**File & class organization:** organize files by functionality (`test_<functionality>.py`); split
scenarios into files. Use a **class** when a cohesive group benefits from shared scope,
parametrization, markers, or context — not as a namespace for otherwise independent tests, and
never by introducing shared mutable state or an incremental chain merely to justify grouping.

**Markers:**

- Team marker `network` and `tier2` are **implicit** — don't add them.
- When a test uses a requirement marker in the hook's enforced set (e.g. `sriov`, `jumbo_frame`),
  declare a covering `@pytest.mark.special_infra`. The enforced set is defined in
  `scripts/pre_commit_hooks/check_test_basics.py` and root `AGENTS.md` — consult it for the current
  list rather than judging what is "special" (the set evolves as implementations change). The hook
  flags *newly added* requirement markers lacking a covering `special_infra`; it does not auto-add
  the marker, and legacy omissions are deliberately preserved. `single_nic` is exempt.
- `nmstate` is added automatically (see §7) — don't add it explicitly.

---

## 7. NMState-dependent tests

*(Current repo behavior.)* NMState-dependent tests are detected via the
`nmstate_dependent_placeholder` fixture and marked dynamically (`utilities/pytest_utils.py`,
`tests/fixtures/network/nmstate.py`); the `nmstate` marker is auto-added. The session check verifies
the `openshift-nmstate` namespace and its pods before running — **don't assume the operator is
present**; verify the target cluster's NMState installation and supported configuration. NMState
dependency ≠ `network/nmstate` tests (any test may use NMState in setup), so these rules live at
`tests/network/`, not a sub-feature directory.

---

## 8. Logging, exceptions & assertions

- **Logging belongs with the operation that performs it.** Put the log in the helper or resource
  method that does the work, so every caller benefits — e.g. the test calls
  `add_pod_interface_and_network(vm=vm)` and *that* helper logs and applies the change; a condition
  waiter owns its wait diagnostics. Remove duplicated test-body / VM-fixture logs; don't create a
  log-only helper. "Log once on final failure" applies to repeated **polling** diagnostics (don't
  dump a process log on every `is_running()` poll) — it does not suppress the normal
  lifecycle/configuration logs root requires.
- **Raise specific exceptions matching the real failure domain** (an iface-status API error is not a
  guest-operation error). Keep volatile values (e.g. a migration timeout) out of exception classes.
  Don't catch-log-reraise when the message is already descriptive — the exception *is* the signal.
- **Assertion ownership** *(delta: network design guidance, compatible with root)*: operational and
  prerequisite-validation helpers **raise** contextual exceptions; observation helpers **return**
  values for the test to assert; test verdicts live in test bodies or in clearly-named, purpose-
  built test-assertion helpers (e.g. `assert_restart_required_condition_not_set` in
  `tests/network/primary_network/attach_primary/libattach.py`). A test-assertion helper must add a
  meaningful verdict, shared assertion logic, or useful diagnostic context — **do not** wrap a
  success-or-raise waiter in an assert-only function just to rename its call. Do not hide verdicts
  in general operations.
- **Use typed spec objects / `ResourceField` over raw dict manipulation**; extract shared constants
  to a location every consumer can reach so duplicated literals can't diverge.

---

## 9. Naming

- **Name by intent/role, not mechanism** — `non_migratable_vm` / `client VM`, not
  `vm_with_data_volume` / `VM-A`. Don't encode implementation detail in a name.
- **Verbs for actions, nouns for resources/fixtures** — `_delete_interfaces`, not `absent`.
- **State units in the name** — `timeout_sec`, `interval` (not a bare `sleep`).
- **Drop prefixes the module already implies** — alias the import instead (`... as nncp`); avoid
  vague module names (`network_tester` → `connectivity` / `traffic_generator`).
- A fixture name must fit **all** its consumers, not just one.

---

## 10. Network deltas from root

Links to the intentional network differences/sharpenings — each is stated in full at its section.
Everything else in root `AGENTS.md` applies unchanged.

- Helper file naming — [§2](#2-code-placement--reuse) *(proposed; reconcile with root on adoption)*
- Shared-code location (`libs/`) — [§2](#2-code-placement--reuse) *(emphasis)*
- Waiting form (`@retry`) — [§4](#4-waiting-polling--connectivity) *(form preference)*
- Assertion ownership — [§8](#8-logging-exceptions--assertions) *(design guidance, compatible with root)*
