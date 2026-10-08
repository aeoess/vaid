<!--
DRAFT. Not posted to GitHub. Allan reviews and decides whether/when to post
this to a2aproject/A2A#2028, and from which account.
-->

The audit/authorization split this thread converged on is right, and we have
one concrete answer for where `proof_ref` points: VAID, an open format for a
signed, attenuated delegation proof.

A VAID is Ed25519-signed, carries its own scope and capabilities, and names
its parent inside the signed bytes. A verifier holding the ancestors checks,
offline: the signature at every hop, that each child's authority is
contained in its parent's (structural, not asserted), that nothing expired,
and revocation via a check that fails closed when unreachable. That is the
resolvable grant proof `proof_ref` needs.

It composes rather than competes. `actorChain` stays the audit record; a hop
sets `proof_ref` (or `credentialRef`, per the ZeroID mapping upthread) to a
VAID's `vaid_id`, and a verifier that understands both resolves it against
the VAID on the same message. A verifier that only knows `actorChain` sees
an opaque reference, consistent with "absence is not a denial."

We have a draft A2A extension for this, with a normative verification order
and six test vectors covering authority, not just shape: a wider-than-parent
child, an expired leaf, a revoked link, an out-of-scope action despite good
attenuation, and an unrecognised issuer key.

- Spec: https://github.com/solara-associates/vaid/blob/feat/a2a-extension/docs/a2a/extension.md
- Vectors: https://github.com/solara-associates/vaid/tree/feat/a2a-extension/docs/a2a/vectors
- Verifier (Python, no a2a-python dependency): https://github.com/solara-associates/vaid/tree/feat/a2a-extension/python/vaid-a2a

All on a branch for now; links move to main once it merges. If anyone here
has their own token format, the vectors are plain JSON and cheap to run
against a second implementation, the negative cases especially.
