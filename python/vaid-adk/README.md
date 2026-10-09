# vaid-adk

VAID verification for Google's Agent Development Kit (ADK): a `BasePlugin`
that checks a presented VAID's signature, expiry, delegation-chain
attenuation and revocation status before an agent runs, before it is
delegated to as a sub-agent, and before it calls a tool. It denies
fail-closed whenever any of that cannot be positively confirmed.

ADK has no built-in mechanism for this (google/adk-python#4992, #6551). This
package adds it for an agent that already carries a VAID
(https://github.com/solara-associates/vaid), using only `vaid_mint`'s
existing signature, chain and revocation primitives. It does not mint
credentials; minting an attenuated child VAID for a sub-agent is the
caller's job, via `vaid_mint.mint.MintService.mint_child`, exactly what
`examples/two_agent_delegation.py` does before wiring the plugin.

## Why a plugin, not a per-agent callback

ADK's `BaseAgent`/`LlmAgent` accept `before_agent_callback` and
`before_tool_callback` directly, and that is the hook an ADK adapter built
in June 2026 (`forge-agents` commit `85fdaa8`, `synthera` commit `dd0503c`)
used for its governed-delegation gate: `before_agent_callback` closing over
one sub-agent's `mint_child` call. That shape, enforce before an agent
runs and before a tool is called, is reused here, but `vaid-adk` registers
through `BasePlugin` instead of per-agent fields, for one reason: a
per-agent callback is opt-in per agent, so an agent constructed without one
runs ungoverned by omission. A `BasePlugin` is registered once on the
`Runner`/`App`, and ADK's `plugin_manager` consults it for every agent and
every tool call in the invocation tree, including a sub-agent added after
the gate was wired, and including ADK's own native delegation
(`transfer_to_agent` / `sub_agents`) with no further code at the call site.

Confirmed directly against the ADK source (`google-adk==2.11.0`):

- `BaseAgent._run_with_lifecycle` calls `self._handle_before_agent_callback(ctx)`
  on **every** `run_async`, which runs `ctx.plugin_manager.run_before_agent_callback`
  before the agent's own canonical callbacks; returning `Content` sets
  `ctx.end_invocation`, skipping the agent entirely, including a sub-agent
  reached through ADK's native delegation loop.
- `_caller.py`'s `_call_tool_async` runs
  `invocation_context.plugin_manager.run_before_tool_callback(tool=tool,
  tool_args=function_args, tool_context=tool_context)` before any canonical
  callback; a non-`None` return becomes the tool's function response
  directly, and the tool itself is never called.

## Usage

```python
from vaid_mint.chain import KernelKeyMap
from vaid_adk import ToolAuthorization, VaidAuthPlugin, VaidPresentation

plugin = VaidAuthPlugin(
    keys=KernelKeyMap([issuer_kernel_public_key]),   # trusted issuer(s)
    revocation=my_revocation_check,                   # see "Production note" below
    tool_authorizations={
        "lookup_order": ToolAuthorization(capability="read", resource="data.orders"),
        "issue_refund": ToolAuthorization(capability="write", resource="data.payments"),
    },
)

# Register the VAID each agent presents: its own signed document (`leaf`)
# plus the ancestor chain back to a trusted root (`chain`), not including
# the leaf itself.
plugin.register("coordinator", VaidPresentation(leaf=root_vaid))
plugin.register("worker", VaidPresentation(leaf=worker_child_vaid, chain=(root_vaid,)))

# runner = Runner(..., plugins=[plugin])
```

A tool with no entry in `tool_authorizations` is **denied**, never allowed
by omission. An agent with no registered presentation is denied the same
way: it is indistinguishable from one that was simply never given an
identity.

## Run the example

```
pip install -e python/vaid-mint
pip install -e python/vaid-adk[test]
python python/vaid-adk/examples/two_agent_delegation.py
```

A coordinator mints an attenuated child VAID for a worker sub-agent (scope
`data.orders` only, capability `read` only, narrower than the coordinator's
own `data.orders` + `data.payments`, `read` + `write`), registers both
agents' presentations with the plugin, and runs them through a real ADK
`Runner`. The worker then attempts two tool calls:

```
[coordinator] delegating to worker
[worker] lookup_order: ALLOWED
[worker] issue_refund: DENIED (out_of_scope)
```

`lookup_order` is within the worker's attenuated `data.orders`/`read`
bounds; `issue_refund` needs `data.payments`/`write`, which the worker's
VAID never held, so the plugin denies it before the tool runs.

## What this package checks, in order

1. The leaf VAID's kernel signature, against a trusted key in `keys`.
2. The leaf's own `expires_at`.
3. The presented chain's integrity and attenuation back to a trusted root
   (`vaid_mint.chain.verify_chain_at`): scope, capabilities, tenant and
   expiry contained at every hop.
4. The specific tool call's mapped `resource`/`capability` against the
   leaf's own `scope_boundary`/`capability_set`.
5. Revocation of every VAID in the assembled lineage, via the
   `RevocationCheck` passed to `VaidAuthPlugin`.

Any step that cannot be positively confirmed denies the call. "Could not
determine" (an unassembled chain, an unavailable revocation store) is never
read as "not revoked"; see `vaid_mint.revocation.RevocationStatus` and
`vaid_mint.verify.VaidVerdict`, whose fail-closed rule this package inherits
rather than re-deciding.

## Production note: wire a real RevocationCheck

`VaidAuthPlugin` takes `revocation` as a **required** constructor argument
with no default. The example above uses
`InMemoryRevocationList.assume_nothing_revoked()` only because it has no
production revocation store to call. That store is non-durable and fails
*open* after a restart (a VAID revoked before the restart verifies clean
again), which is fine for a demo and wrong for anything that must survive
one. For production, inject a durable `RevocationCheck` backed by your own
revoked-credential store (see `vaid_mint.revocation.RevocationBackend` for
the reference shape: both the revoked-set half and the lineage-resolver half
durable together, never one without the other) and let it report
`RevocationStatus.UNAVAILABLE` whenever it cannot be reached; this plugin
already denies on that outcome.

## What this package does not do

- **It does not mint.** Issuing a root VAID or an attenuated child VAID for
  a sub-agent is ordinary `vaid_mint` usage (`MintService.mint_root` /
  `mint_child`), done by the caller before `VaidAuthPlugin.register` is
  called.
- **It does not depend on `forge-agents` or `synthera`.** The June 2026 ADK
  adapters in those repos are prior art for the hook choice; this package
  reuses only `vaid_mint`.
- **It does not depend on `vaid-a2a`.** The verification order in
  `vaid_adk._verify` mirrors `vaid_a2a.verifier.verify_a2a_message`'s order
  deliberately (both are "how do you check a presented VAID end to end"),
  but each is self-contained against `vaid_mint` rather than one importing
  the other.

## Install

**Local dev only**, from a repo checkout:

```
pip install -e python/vaid-pop
pip install -e python/vaid-mint
pip install -e python/vaid-adk[test]
```
