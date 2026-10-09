# Session 310 report: vaid-adk, VAID verification for Google ADK

Branch: `feat/vaid-adk`. PR: https://github.com/solara-associates/vaid/pull/110

## ADK version and the hook used

Verified against `google-adk==2.11.0` (PyPI latest at session time, installed
into a throwaway venv and inspected directly, not from memory).

ADK has two relevant extension points on `google.adk.plugins.base_plugin.BasePlugin`:

```python
async def before_agent_callback(
    self, *, agent: BaseAgent, callback_context: CallbackContext
) -> Optional[types.Content]: ...

async def before_tool_callback(
    self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict[str, Any]]: ...
```

Confirmed in the installed source, not asserted from the type hints alone:

- `BaseAgent._run_with_lifecycle` (`google/adk/agents/base_agent.py`) calls
  `self._handle_before_agent_callback(ctx)` on every `run_async`, which runs
  `ctx.plugin_manager.run_before_agent_callback` ahead of the agent's own
  canonical `before_agent_callback` list. Returning `Content` sets
  `ctx.end_invocation = True`, which skips the agent's `_run_async_impl`
  entirely. This fires identically whether the agent is the root or a
  sub-agent reached through ADK's native in-process delegation
  (`sub_agent.run_async(ctx)`, or `transfer_to_agent`), because every agent's
  `run_async` goes through the same lifecycle wrapper.
- `google/adk/flows/llm_flows/tools/_caller.py`'s tool-calling path runs
  `invocation_context.plugin_manager.run_before_tool_callback(tool=tool,
  tool_args=function_args, tool_context=tool_context)` before any canonical
  `before_tool_callback`. A non-`None` return becomes the function response
  directly; the tool itself is never invoked.

`BasePlugin` is registered once on the `Runner`/`App` (`plugins=[...]`), so
these fire for every agent and every tool call in the invocation tree with no
further code at each call site; a per-agent `before_agent_callback` field
would be opt-in per agent and could be omitted on a sub-agent added later.
That is the design reason `vaid-adk` uses `BasePlugin` rather than the
per-agent fields the June adapters used (see below).

I also read google/adk-python#4992 and #6551 directly (not from memory): both
are third-party pitches for cryptographic agent-identity verification before
delegation/tool access (`AgentID`/`getagentid`, and `CreduentGoogleADKPlugin`
from the `creduent` package), neither merged, both acknowledged by maintainers
as "under review" with no further movement. This confirms there is still no
first-party ADK mechanism for this, which is the premise the brief asked me to
verify before building anything (halt condition: "No suitable ADK hook exists
in the current release" did not apply; the stable hooks above exist and I
exercised them directly against real ADK source, not just the type hints).

## What was reused from the June 2026 adapters, and what changed

Read `forge-agents` commit `85fdaa8` (`templates/agent/adk/synthera_agent/delegation.py`)
and `synthera` commit `dd0503c` (`integrations/synthera-adk/synthera_adk/delegation.py`)
directly. The commit hashes given in the brief (`9c21169` for forge-agents,
`37b64a0` for synthera) do not exist in either repo's history (checked after
an `--unshallow` fetch against `git log --oneline --all`); these are the real
commits implementing the ADK adapter phase the brief is pointing at.

**Reused:** the hook choice itself. `before_agent_callback` is exactly where
both adapters put their governed-delegation gate, and the mechanism they
relied on (returning `Content` makes ADK skip the agent, read as
`end_invocation`) is the same mechanism I confirmed in the current ADK
source and the same mechanism `vaid-adk`'s `before_agent_callback` uses.

**Changed:**

- Those adapters are *minting* gates (`before_agent_callback` closes over a
  `mint_child` call and writes a freshly minted transport into a private
  `_Cell` mailbox the sub-agent reads). `vaid-adk` is a *verification* gate
  only: it has no mint call and no knowledge of how a VAID was produced. It
  checks a presentation (`leaf` + `chain`) that the caller registers.
- Those adapters wired the gate as a **per-sub-agent field**
  (`GovernedSubAgent(..., before_agent_callback=_governed_gate(parent, deleg, cell))`),
  built fresh for each delegation. `vaid-adk` wires it as a **`BasePlugin`**,
  registered once, because the task calls for "denies the tool call or
  delegation when verification fails" as a property of the integration, not
  of each sub-agent's construction; a `BasePlugin` cannot be forgotten on a
  new sub-agent the way a per-agent field can.
- Those adapters' no-ungoverned-transport invariant depends on pydantic's
  `extra='forbid'` on `BaseAgent`, since a transport is state the agent
  itself would otherwise carry. `vaid-adk` carries no state on the agent at
  all; VAID presentations live in the plugin's own registry, keyed by ADK
  agent name, so there is nothing on the agent object to fabricate.
- `before_tool_callback` is new here. The June adapters did not gate tool
  calls (their worker agent's `_run_async_impl` called `transport.evaluate_policy`
  directly rather than going through ADK's LLM-driven tool-call path); the
  brief asks for tool-call authorization specifically, which needed the second
  hook.

`vaid-adk` has no dependency on `forge-agents` or `synthera` (only on
`vaid_mint`), as instructed.

## Design decisions

- **`BasePlugin`, not per-agent callbacks.** See above.
- **Fail closed, explicitly, at three points with no default:** (1) no
  registered VAID presentation for an agent denies it, (2) a tool with no
  entry in the required `tool_authorizations` map denies it (never
  default-allow), (3) `revocation` is a required constructor argument with
  no default value and no built-in fail-open convenience method exposed from
  this package (the fail-open `assume_nothing_revoked()` the examples/tests
  use comes from `vaid_mint.revocation` itself, named explicitly there, not
  reintroduced here).
- **Verification logic (`vaid_adk/_verify.py`) is self-contained against
  `vaid_mint`,** not a dependency on `vaid_a2a`. The order (leaf
  authenticity, leaf expiry, chain integrity/attenuation, requested
  resource/capability, lineage revocation) deliberately mirrors
  `vaid_a2a.verifier.verify_a2a_message`'s order, because that is already
  the estate's answer to "how do you check a presented VAID end to end," but
  it is a second, independent implementation against the same `vaid_mint`
  primitives rather than an import of the (currently privately-patched)
  `vaid-a2a` package. `python/vaid-a2a` was not touched.
- **Tool authorization mapping is explicit and required** (`ToolAuthorization(capability=..., resource=...)`
  per tool name), checked against the leaf's own `scope_boundary`/`capability_set`
  via the existing `vaid_mint.document.is_in_scope`/`has_capability` matchers,
  not reimplemented.

## Tests

13 tests, fixed seeds (`Ed25519PrivateKey.from_private_bytes(bytes([...]) * 32)`),
fixed verification time (`datetime(2026, 7, 1, tzinfo=timezone.utc)`) for the
scenarios that need a clock:

- `tests/test_adk_verify.py` (7): allowed tool call, out-of-scope/missing-capability
  denied, expired leaf denied, revoked-parent-denies-child, missing VAID
  denied, wider-than-parent child denied, revocation-unavailable denied
  (indeterminate, fails closed).
- `tests/test_plugin.py` (6): `before_agent_callback`/`before_tool_callback`
  dispatch through the real `BasePlugin` method signatures with minimal
  duck-typed Agent/Tool/ToolContext stand-ins (the plugin reads only `.name`
  and `.agent_name` from them): unmapped tool denied, unregistered agent
  denied, authorized call allowed, call outside capability set denied,
  missing VAID denied at the tool-call site too.

`python -m pytest python/vaid-pop python/vaid-mint python/vaid-langchain python/vaid-a2a python/vaid-adk`:
**234 passed**, 0 failed, run together exactly as CI's `python` job does.

`examples/two_agent_delegation.py` runs a real ADK `Runner` (no model/API
key: two plain `BaseAgent` subclasses act without an LLM) and produces
exactly the output shown in the README:

```
[coordinator] delegating to worker
[worker] lookup_order: ALLOWED
[worker] issue_refund: DENIED (out_of_scope)
```

## CI status

All checks pass except one, which is a deliberate, instructed gap, not a
defect:

**`release-map` job fails on this branch.** `scripts/verify-release-map.mjs`
requires every package under `python/` with a `pyproject.toml` to have a
`release-map.json` entry; `vaid-adk` was explicitly instructed not to have
one. Confirmed locally (`node scripts/verify-release-map.mjs`) and on CI
(job "Every publishable package is reachable by the release workflow", PR
#110). I did not work around this by adding the entry, since that would
contradict the explicit instruction; I did not modify the check script,
since that would weaken a gate that protects every other package in the
repo for a reason unrelated to this branch.

**A second, separate check needed action and was not covered by the "don't
touch release-map.json" instruction:** `scripts/verify-package-versions.mjs`
maintains its own `REGISTRY_SCOPE` list (distinct file, distinct purpose:
"every package in the tree must declare whether it is meant to reach a
registry", guarding against a package silently never being published rather
than against a release tag resolving to the wrong directory). This failed
first ("Capabilities manifest & claims-register verified" job) because
`vaid-adk` was undeclared there. `python/vaid-a2a` already has an entry in
this exact list, so, per the brief's instruction to follow the vaid-a2a
pattern when CI requires something, I added one line mirroring it:
`{ registry: 'pypi', dir: 'python/vaid-adk', name: 'vaid-adk' }`. This is not
`release-map.json` and does not register the package for release; it only
states "this package is pypi-shaped and known," which is the same thing
`verify-release-map.mjs`'s own completeness check does for `vaid-a2a` already
(an entry that exists without any corresponding CI build/publish job, since
neither `vaid-a2a` nor `vaid-adk` is wired into `release.yml`). Pushed as a
separate commit (`02db369`) so the two concerns stay distinguishable in
history.

All other jobs pass: Rust conformance, Python conformance (pytest, which
includes `vaid-adk`'s 13 new tests), TypeScript conformance, all 8
drift-check/conformance jobs, name-guard, README-drift, release-workflow
structure, vaid-skill, and (after the fix above) capabilities/claims-register.

## Halt conditions checked, none triggered

- ADK hook: exists and was verified directly against installed source
  (`google-adk==2.11.0`), not assumed. No halt.
- No `vaid_mint` core change was needed; `vaid-adk` only calls existing
  public `vaid_mint` functions. No halt.
- The one CI failure (`release-map`) is a deliberate consequence of this
  branch's explicit brief, not a failure "for a reason outside this branch."
  Documented above rather than treated as a halt.

## Not done, by instruction

- `python/vaid-a2a` was not touched.
- `release-map.json` was not edited.
- Nothing was merged, tagged, bumped, released or published. No push to
  `main`. No post outside `solara-associates/vaid`.
- `docs/drafts/adk-4992-comment.md` is a draft only; nothing was posted to
  GitHub issues #4992 or #6551.
