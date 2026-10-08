"""Unit tests for vaid_a2a.verifier behaviour not exercised by the shared
vectors in docs/a2a/v1/vectors/ — metadata presence/shape and the revocation-
unavailable fail-closed path."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from vaid_a2a import METADATA_CHAIN_KEY, METADATA_VAID_KEY, VerifyCode, verify_a2a_message
from vaid_mint.document import (
    build_unsigned_vaid_document,
    canonical_vaid_signing_bytes,
    compute_lineage_hash,
)
from vaid_mint.issuer_identity import kernel_key_thumbprint
from vaid_mint.revocation import InMemoryRevocationList

_KEY = Ed25519PrivateKey.from_private_bytes(bytes([0x7]) * 32)
_PUBLIC = _KEY.public_key().public_bytes_raw()
_THUMBPRINT = kernel_key_thumbprint(_PUBLIC)
NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


TRUST_CONFIG = {
    "trustedIssuers": [{"trustDomain": "vaid.example", "kernelPublicKey": _b64url(_PUBLIC)}]
}


def _leaf(agent_id: str, scope: list[str]) -> dict:
    unsigned = build_unsigned_vaid_document(
        vaid_id=agent_id,
        agent_id=agent_id,
        agent_class="test",
        version="1.0.0",
        tenant_id="t",
        issued_at="2026-06-04T12:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        public_key_der=list(range(32)),
        parent_vaid=None,
        scope_boundary=scope,
        lineage_hash=compute_lineage_hash(None, agent_id),
        capability_set=["read"],
        trust_domain="vaid.example",
        kernel_key_thumbprint=_THUMBPRINT,
    )
    signature = _KEY.sign(canonical_vaid_signing_bytes(unsigned))
    return {**unsigned, "kernel_signature": list(signature)}


def test_no_vaid_passes_through_when_not_required() -> None:
    result = verify_a2a_message(
        {"metadata": {}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList.assume_nothing_revoked(),
        now=NOW,
    )
    assert result.allowed is True
    assert result.code is VerifyCode.NO_VAID


def test_no_vaid_denied_when_required() -> None:
    result = verify_a2a_message(
        {"metadata": {}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList.assume_nothing_revoked(),
        require_vaid=True,
        now=NOW,
    )
    assert result.allowed is False
    assert result.code is VerifyCode.NO_VAID


def test_malformed_vaid_metadata_is_unparseable() -> None:
    result = verify_a2a_message(
        {"metadata": {METADATA_VAID_KEY: "not-an-object"}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList.assume_nothing_revoked(),
        now=NOW,
    )
    assert result.allowed is False
    assert result.code is VerifyCode.UNPARSEABLE


def test_malformed_chain_metadata_is_unparseable() -> None:
    leaf = _leaf(str(uuid.uuid4()), ["data.acme"])
    result = verify_a2a_message(
        {"metadata": {METADATA_VAID_KEY: leaf, METADATA_CHAIN_KEY: "not-a-list"}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList.assume_nothing_revoked(),
        now=NOW,
    )
    assert result.allowed is False
    assert result.code is VerifyCode.UNPARSEABLE


def test_revocation_unavailable_fails_closed() -> None:
    """An absent (never-populated) revocation store must deny, never be read
    as not-revoked — R.4.5's fail-closed default, exercised at the extension
    layer rather than only inside vaid_mint itself."""
    leaf = _leaf(str(uuid.uuid4()), ["data.acme"])
    result = verify_a2a_message(
        {"metadata": {METADATA_VAID_KEY: leaf}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList(),  # absent: never revoked into, never populated
        now=NOW,
    )
    assert result.allowed is False
    assert result.code is VerifyCode.INDETERMINATE


def test_no_requested_action_skips_scope_check() -> None:
    leaf = _leaf(str(uuid.uuid4()), ["data.acme.orders"])
    result = verify_a2a_message(
        {"metadata": {METADATA_VAID_KEY: leaf}},
        trust_config=TRUST_CONFIG,
        revocation=InMemoryRevocationList.assume_nothing_revoked(),
        requested_action=None,
        now=NOW,
    )
    assert result.allowed is True
    assert result.code is VerifyCode.ALLOWED
