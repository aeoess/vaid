# Changelog

All notable changes to the Python `vaid-a2a` package are documented here.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This package versions **independently** of `vaid-pop`, `vaid-mint` and
`vaid-langchain`; a shared version number between them is a coincidence, not
a guarantee.

## [0.1.0]

Initial draft: a reference verifier for the VAID A2A extension
(`docs/a2a/v1/extension.md`, status: draft). Exposes one function,
`verify_a2a_message`, over the existing `vaid_mint` primitives — no
`a2a-python` dependency, `Message` accepted as a plain `dict`.

Checks, in order: signature/authenticity, leaf expiry, chain integrity,
per-hop attenuation, requested-action scope, revocation. Fails closed on
every "could not determine" case, never folding it into a pass or a
specific denial.

Not released. Not registered for independent publication outside this
repository's own release workflow.
