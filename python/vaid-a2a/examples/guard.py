"""A minimal example: use vaid_a2a.verify_a2a_message as a guard in front of
an A2A request handler. Not wired to any specific A2A server framework —
`handle_message` below is the shape any framework's message handler takes.
"""

from __future__ import annotations

from vaid_a2a import METADATA_VAID_KEY, VerifyCode, verify_a2a_message
from vaid_mint.revocation import RevocationCheck

# Loaded once at startup from the AgentCard's own extension declaration.
TRUST_CONFIG = {
    "trustedIssuers": [
        {"trustDomain": "vaid.example", "kernelPublicKey": "<base64url, raw 32 bytes>"},
    ]
}


def handle_message(message: dict, revocation: RevocationCheck) -> dict:
    """A stand-in for a real A2A message handler. ``message`` is the incoming
    A2A ``Message`` as a dict; ``action`` is whatever this handler is about
    to do, used as the ``requested_action`` scope check."""
    action = "data.acme.orders"

    result = verify_a2a_message(
        message,
        trust_config=TRUST_CONFIG,
        revocation=revocation,
        requested_action=action,
    )

    if not result.allowed:
        # result.code is a VerifyCode — map it to whatever error shape this
        # handler's A2A transport expects (see docs/a2a/v1/extension.md §6).
        return {
            "error": {
                "code": result.code.value,
                "message": result.reason,
            }
        }

    if result.code is VerifyCode.NO_VAID:
        # The extension was not activated, or carried no VAID, and
        # requireVaid was false — this handler's own policy decides whether
        # that is acceptable for this action. Shown here for completeness;
        # a handler that requires a VAID for every action should instead
        # pass require_vaid=True above and never reach this branch.
        pass

    return {"result": f"handled action {action!r}"}


if __name__ == "__main__":
    print(METADATA_VAID_KEY)
