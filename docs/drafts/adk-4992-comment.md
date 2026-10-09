We built a third-party package addressing this and the related #6551:
`vaid-adk` (https://github.com/solara-associates/vaid/tree/main/python/vaid-adk,
branch `feat/vaid-adk`, not yet released).

It is a `BasePlugin` checking a presented VAID
(https://github.com/solara-associates/vaid) before an agent runs, before
delegation to a sub-agent, and before any tool call: kernel Ed25519 signature,
the leaf's own expiry, delegation-chain integrity and attenuation back to a
trusted root (no child claims wider scope or capabilities than its parent), the
tool's mapped resource/capability against the leaf's own bounds, and
revocation across the lineage. Any step that cannot be positively confirmed
denies the call; there is no default-allow path. It registers through
`before_agent_callback` and `before_tool_callback` (checked against
`google-adk==2.11.0`), both firing for every agent run and tool call, including
ADK's native delegation, so no later sub-agent goes ungoverned by omission.

It verifies and authorizes only; it does not mint. Minting an attenuated child
VAID is ordinary use of the existing `vaid_mint` package.

VAID can also be minted over a SPIFFE workload identity, so this complements
SPIFFE-based Agent Identity work rather than replacing it.

Given the number of similar proposals open here and in #6551, would the ADK
team prefer this stay an external package, or would a contributed sample be
more useful?
