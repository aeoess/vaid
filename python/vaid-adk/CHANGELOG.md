# Changelog

All notable changes to the Python `vaid-adk` package are documented here.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This package versions **independently** of `vaid-mint`; a shared version
number between them is a coincidence, not a guarantee.

## [0.1.0]

Initial release: VAID verification for Google ADK.

A `BasePlugin` (`VaidAuthPlugin`) that verifies a presented VAID's
signature, expiry, delegation-chain attenuation and revocation status before
an ADK agent runs, before it is delegated to as a sub-agent, and before any
tool call. It maps the verified leaf's `scope_boundary` and
`capability_set` onto the tool being called via a required
`tool_authorizations` map, and denying fail-closed whenever any check
cannot be positively confirmed (missing VAID, unmapped tool, expired leaf,
unattenuated chain, unavailable revocation).

Depends only on `vaid-mint>=0.9.0` and `google-adk>=2.0,<3`. Reuses the
hook choice (`before_agent_callback` for delegation gating) proven in the
June 2026 ADK adapters in `forge-agents` (commit `85fdaa8`) and `synthera`
(commit `dd0503c`), extended to `before_tool_callback` for per-tool
authorization and registered through `BasePlugin` rather than per-agent
fields so no agent can be forgotten. Mints nothing; verification only.

This is the only released version to date.
