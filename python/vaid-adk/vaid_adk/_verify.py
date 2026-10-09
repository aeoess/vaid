"""VAID standing verification for a presented identity: leaf + ancestor chain.

Self-contained, built only on ``vaid_mint`` primitives (no dependency on
``vaid_a2a`` — that package has its own release cadence and is not something
this package should couple to). The verification order mirrors
``vaid_a2a.verifier.verify_a2a_message`` because that order is already the
estate's answer to "how do you check a presented VAID end to end": authenticity
of the leaf, leaf expiry, chain integrity and attenuation back to a trusted
root, revocation over the full assembled lineage. This module re-derives that
order against the same ``vaid_mint`` functions rather than importing the other
package's implementation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

from vaid_mint.attestation import AttestationBundle
from vaid_mint.chain import (
    ChainVerification,
    KernelKeyResolver,
    PresentedBundle,
    verify_chain_at,
)
from vaid_mint.document import has_capability, is_expired_at, is_in_scope
from vaid_mint.revocation import RevocationCheck, RevocationStatus, assemble_lineage
from vaid_mint.verify import VaidVerdict, verify_vaid_authenticity_graded


class VerifyCode(enum.Enum):
    """Why :func:`verify_presentation` allowed or denied — the reason
    alongside the boolean. A caller that can only see a boolean cannot log,
    alert, or retry "forged" differently from "could not reach the revocation
    store"."""

    ALLOWED = "allowed"
    NO_VAID = "no_vaid"
    UNSUPPORTED_SIG_VERSION = "unsupported_sig_version"
    MALFORMED_TRUST_DOMAIN = "malformed_trust_domain"
    ISSUER_MISMATCH = "issuer_mismatch"
    LINEAGE_INCONSISTENT = "lineage_inconsistent"
    INAUTHENTIC = "inauthentic"
    EXPIRED = "expired"
    UNVERIFIABLE = "unverifiable"
    NOT_ATTENUATED = "not_attenuated"
    CONSENT_EXPIRED = "consent_expired"
    OUT_OF_SCOPE = "out_of_scope"
    MISSING_CAPABILITY = "missing_capability"
    REVOKED = "revoked"
    INDETERMINATE = "indeterminate"

    @property
    def is_determined_denial(self) -> bool:
        """True for a positive refusal; false for :attr:`ALLOWED` and
        :attr:`INDETERMINATE` — "could not tell" is a refusal but not an
        accusation, mirroring :attr:`~vaid_mint.verify.VaidVerdict.INDETERMINATE`."""
        return self not in (VerifyCode.ALLOWED, VerifyCode.INDETERMINATE)


@dataclass(frozen=True)
class VerifyResult:
    """The outcome of :func:`verify_presentation`. ``allowed`` is the field a
    gate checks first; ``code`` and ``reason`` are for the caller that logs or
    audits a denial."""

    allowed: bool
    code: VerifyCode
    reason: str


def _allow(code: VerifyCode, reason: str) -> VerifyResult:
    return VerifyResult(allowed=True, code=code, reason=reason)


def _deny(code: VerifyCode, reason: str) -> VerifyResult:
    return VerifyResult(allowed=False, code=code, reason=reason)


_AUTHENTICITY_VERDICT_TO_CODE: dict[VaidVerdict, VerifyCode] = {
    VaidVerdict.UNSUPPORTED_SIG_VERSION: VerifyCode.UNSUPPORTED_SIG_VERSION,
    VaidVerdict.MALFORMED_TRUST_DOMAIN: VerifyCode.MALFORMED_TRUST_DOMAIN,
    VaidVerdict.ISSUER_MISMATCH: VerifyCode.ISSUER_MISMATCH,
    VaidVerdict.LINEAGE_INCONSISTENT: VerifyCode.LINEAGE_INCONSISTENT,
    VaidVerdict.INAUTHENTIC: VerifyCode.INAUTHENTIC,
}

_CHAIN_VERDICT_TO_CODE: dict[ChainVerification, VerifyCode] = {
    ChainVerification.INAUTHENTIC: VerifyCode.INAUTHENTIC,
    ChainVerification.UNVERIFIABLE: VerifyCode.UNVERIFIABLE,
    ChainVerification.NOT_ATTENUATED: VerifyCode.NOT_ATTENUATED,
    ChainVerification.EXPIRED: VerifyCode.EXPIRED,
    ChainVerification.CONSENT_EXPIRED: VerifyCode.CONSENT_EXPIRED,
}


@dataclass(frozen=True)
class VaidPresentation:
    """What one ADK agent presents as its identity: its own signed VAID
    document (``leaf``) plus the ancestor documents it is holding so a
    verifier can walk the chain back to a trusted root (``chain``, not
    including ``leaf`` itself — the detached-chain-presentation convention of
    ``vaid_mint.chain`` / the VAID A2A extension)."""

    leaf: dict
    chain: tuple[dict, ...] = ()


def verify_presentation(
    presentation: VaidPresentation | None,
    *,
    keys: KernelKeyResolver,
    revocation: RevocationCheck,
    requested_resource: str | None = None,
    requested_capability: str | None = None,
    now: datetime | None = None,
) -> VerifyResult:
    """Verify a presented VAID end to end: authenticity, leaf expiry, chain
    integrity and attenuation back to a trusted root, the specific
    resource/capability this call requires (if given), and revocation over
    the full assembled lineage.

    Returns a refusal — never raises — for a missing or malformed
    presentation. ``presentation is None`` is :attr:`VerifyCode.NO_VAID`, and
    this module has no "pass through" posture for it: unlike the A2A
    extension's ``requireVaid`` switch, a caller invoking this function has
    already decided a VAID is required, so a missing one is always denied.
    """
    now = now or datetime.now(timezone.utc)

    if presentation is None:
        return _deny(VerifyCode.NO_VAID, "no VAID presented")

    leaf = presentation.leaf

    # Step 1: authenticity of the LEAF, resolved ahead of verify_chain_at so an
    # unrecognised issuer is distinguishable from a recognised issuer whose
    # signature does not verify (mirrors vaid_a2a.verifier).
    thumbprint = leaf.get("kernel_key_thumbprint")
    key = keys.resolve_key(thumbprint) if isinstance(thumbprint, str) else None
    if key is None:
        return _deny(
            VerifyCode.ISSUER_MISMATCH,
            f"no trusted kernel key for thumbprint {thumbprint!r}",
        )
    authenticity = verify_vaid_authenticity_graded(key, leaf)
    if authenticity is not VaidVerdict.VALID:
        code = _AUTHENTICITY_VERDICT_TO_CODE.get(authenticity, VerifyCode.INAUTHENTIC)
        return _deny(code, f"leaf authenticity check failed: {authenticity.code}")

    # Step 2: leaf expiry. verify_chain_at deliberately does not check the
    # leaf's own expiry (only ancestors), so it is checked here.
    if is_expired_at(leaf, now):
        return _deny(VerifyCode.EXPIRED, "leaf VAID has passed its own expires_at")

    # Steps 3/4: chain integrity back to a trusted root, and per-hop
    # attenuation (scope, capabilities, tenant, expiry).
    bundle = PresentedBundle(presentation.chain)
    chain_verdict = verify_chain_at(keys, leaf, bundle, AttestationBundle(), now)
    if chain_verdict is not ChainVerification.ATTENUATED:
        code = _CHAIN_VERDICT_TO_CODE.get(chain_verdict, VerifyCode.UNVERIFIABLE)
        return _deny(code, f"chain verification did not attenuate: {chain_verdict.value}")

    # Step 5: the specific action this call requires is within the LEAF's own
    # scope_boundary / capability_set. Deliberately not subsumed by step 4: a
    # well-attenuated chain says nothing about whether this leaf's own bounds
    # cover the thing being asked of it right now.
    if requested_resource is not None and not is_in_scope(leaf, requested_resource):
        return _deny(
            VerifyCode.OUT_OF_SCOPE,
            f"requested resource {requested_resource!r} is outside the leaf's "
            "scope_boundary",
        )
    if requested_capability is not None and not has_capability(leaf, requested_capability):
        return _deny(
            VerifyCode.MISSING_CAPABILITY,
            f"requested capability {requested_capability!r} is not in the "
            "leaf's capability_set",
        )

    # Step 6: revocation of every link, via the caller's RevocationCheck. The
    # verifier assembles the lineage; the check only answers about a lineage
    # it is handed (vaid_mint.revocation's division of labour).
    lineage = assemble_lineage(leaf, bundle)
    if lineage is None:
        return _deny(
            VerifyCode.INDETERMINATE,
            "lineage could not be completely assembled from the presented "
            "chain — standing cannot be determined, fails closed",
        )
    status = revocation.check_lineage(lineage)
    if status is RevocationStatus.REVOKED:
        return _deny(VerifyCode.REVOKED, "a VAID in the lineage is revoked")
    if status is RevocationStatus.UNAVAILABLE:
        return _deny(
            VerifyCode.INDETERMINATE,
            "revocation check unavailable — fails closed, never read as "
            "not-revoked",
        )

    return _allow(
        VerifyCode.ALLOWED,
        "signature, expiry, chain integrity, attenuation, requested action "
        "and revocation all checked clean",
    )
