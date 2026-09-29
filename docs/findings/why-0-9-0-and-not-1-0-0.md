# Why this release is 0.9.0 and not 1.0.0

**Date:** 2026-09-29
**Repo:** `vaid`
**Status:** CLOSED 2026-09-29. **Decision: 0.9.0.** Taken by the release owner in
session 271, reversing a stated leaning towards 1.0.0 on the ground that the
premise behind that leaning was wrong.
**Applies to:** `vaid-mint` 0.9.0, PR #75.

This is recorded so the question is not re-opened without new information. If you
are about to argue for 1.0.0, read the condition at the end first: there is a
version of that argument which is correct, and it is not the one that was made.

---

## The question

`vaid-mint` 0.9.0 carries two breaking changes: the default revocation posture
flips to fail-closed, and `with_revocation_check` is removed. A consumer who
upgrades without reading finds that a bare `ReferenceIssuer` no longer verifies
what it just minted.

The leaning was 1.0.0, on the ground that pip consumers are unprotected and this
is a security-relevant breaking change.

## The premise that decided it

Per ecosystem, what an existing 0.8.0 pin does when 0.9.0 appears:

| Ecosystem | Typical pin | Resolves onto 0.9.0? |
| --- | --- | --- |
| Cargo | `vaid-mint = "0.8"` | No. Caret on 0.x pins the minor. |
| npm | `^0.8.0` | No. Caret on 0.x pins the minor. |
| pip | `vaid-mint>=0.8.0`, or unpinned | **Yes.** |

The exposure is real and it is one ecosystem. But **1.0.0 does not fix it**.
PyPI's resolver reads `>=0.8.0` as `>=`. It does not read major versions
specially, so `>=0.8.0` resolves onto 1.0.0 exactly as it resolves onto 0.9.0.

Only `==`, `~=`, an upper bound, or a lockfile protects that consumer.

So the pip exposure is an argument for fixing pin advice and publishing an
advisory. It is not an argument for any particular version number. This was the
error in the original leaning and it is the whole reason the decision went the
other way.

## What 1.0.0 would have committed us to

SemVer 2.0.0 section 4 says 0.y.z means anything may change at any time. 1.0.0
replaces that with a promise: no breaking change without a major bump.

What that promise would have cost, read from this package's own history:

| Release | Breaking? |
| --- | --- |
| 0.2.0 | Yes, two traits renamed |
| 0.3.0 | Yes, VAID v3, `mint_v1` re-frozen |
| 0.5.0 | Yes, scope grammar |
| 0.7.0 | Yes, `issued_at()` / `expires_at()` return types |
| 0.8.0 | Yes, three of them, child expiry containment |
| 0.9.0 | Yes, two of them |

Six of the last eight minor releases carried a breaking change. At that cadence
1.0.0 is followed by 2.0.0, 3.0.0 and 4.0.0 within a year. A major version that
turns over every few weeks tells a consumer less than an honest 0.x, and trains
them to ignore the number.

Second, 1.0.0 on a **standard** implies the wire contract is settled. It is not.
Signature algorithm agility is live work and is expected to add a second
algorithm to the conformance surface.

Third, the public status of VAID is Available. 1.0.0 is the number for a
stability declaration, and publishing it would put the registries ahead of the
claims register.

## What protects consumers instead

None of this is the version number's job:

1. Publish the advisory for the fail-open default. An advisory reaches a pip
   consumer through their scanner whatever their pin says, and reaches them
   whether the number is 0.9.0 or 1.0.0.
2. Fix the pip pin advice in the READMEs and the skill to `==` or `~=`, not a
   bare name and not `>=`. This is the only change that reaches the exposed
   consumer directly.
3. State the exposure in the first line of the release note, not the fourth
   section.

## The condition under which 1.0.0 becomes right

The argument for 1.0.0 that is **not** wrong: a package that breaks six times in
eight minors may be sitting at 0.x because 0.x is comfortable, not because the
contract is unsettled, and staying there indefinitely is its own dishonesty.

If that is the case being made, then the coherent package is **1.0.0 together
with a written stability commitment** in `CONTRIBUTING.md` and the spec, with the
breaking-change budget it implies actually enforced.

**1.0.0 without that commitment written down is the worst of both**: it takes on
the promise's cost in consumer expectation while retaining none of its
discipline. A proposal to go to 1.0.0 should therefore be judged on whether the
stability commitment ships with it, and rejected if it does not.

Revisit once algorithm agility has landed and the conformance surface has stopped
moving, and make it a decision about the contract rather than about one release's
blast radius.
