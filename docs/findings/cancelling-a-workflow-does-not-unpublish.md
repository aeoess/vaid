# Cancelling a workflow does not un-publish

**Date:** 2026-09-29
**Repo:** `vaid`
**Status:** CLOSED. The mismatch it caused was repaired the same day; the lesson is
the reason this file exists.
**Applies to:** `vaid-mint` 0.9.0, npm leg. Relevant to every release this
workflow performs.

**The lesson in one line: cancelling a workflow run does not un-publish what it
has already uploaded, and a registry can finalise an upload after the job that
started it is dead.**

---

## What happened

The npm leg of `vaid-mint` 0.9.0 was published twice over, in a sense: once by a
run that was cancelled and reported as cancelled, and not at all by the run that
was supposed to do it.

| Time (UTC) | Event |
| --- | --- |
| 11:03:29 | A tag `npm-vaid-mint-v0.9.0` is pushed at `f352380`. Nobody in the session that was running the release pushed it. |
| ~11:06 | The tag is noticed. It predates a fix to the release workflow's resolvability gate that was explicitly meant to land first, so the run is cancelled and the tag deleted. Nothing had published: npm still served 0.8.0 as `latest`. |
| 11:09:20 | The cancelled run's `npm publish` step had already started. |
| 11:09:41 | The step is killed. The job records `cancelled`. |
| **11:11:47** | **npm records `vaid-mint@0.9.0` as published.** Two minutes after the job that uploaded it was killed. |
| 11:10:32 | The gate fix merges as `243c19a`. |
| ~11:11 | The tag is re-created at `243c19a` and pushed. |
| 11:13:14 | The new run's `npm publish` runs and fails: `You cannot publish over the previously published versions: 0.9.0`. |

The cancellation was submitted while the publish job was still showing as waiting
on its environment gate. It killed the step. It did not reach npm, which had
already accepted the upload.

## The damage, which was not the bytes

The published tarball was correct. Its shasum `8b4da089…` is exactly what the
second run independently rebuilt from a different commit, which is a stronger
reproducibility result than the release normally produces.

The damage was to **provenance**. The SLSA attestation npm holds names:

```
gitCommit  f352380edc7d42654063de3b3191fe8b743c6f67
ref        refs/tags/npm-vaid-mint-v0.9.0
```

and the tag had been re-created at `243c19a`. So the tag a consumer resolves and
the commit the registry attests were different commits. Anyone verifying
provenance against the tag would have found a mismatch, and the mismatch was
introduced by the repair, not by the incident.

The two commits differ only in `.github/workflows/release.yml` and
`docs/capabilities.json`, and in zero files under `typescript/`, which is why the
bytes were identical. That is a reason the mismatch was harmless, not a reason it
was acceptable: a provenance check does not read a diff, it compares hashes.

**Repaired** by force-moving the tag back to `f352380`, the commit the artifact
was actually built from. All three release tags for 0.9.0 now resolve to that one
commit, and it matches the attested commit and the attested ref.

## What to do differently

1. **Never cancel a release run to stop a publish.** By the time a publish step is
   running it is too late; cancelling only removes your ability to see what it
   did. Let it finish and read the result. If the wrong thing publishes, the
   remedies are yank, deprecate or a new version, all of which are visible.
2. **Check whether anything published before concluding a cancelled run did
   nothing.** A job that says `cancelled` is a statement about the job, not about
   the registry. Ask the registry.
3. **A tag is a claim about which commit produced an artifact.** Do not re-point a
   release tag at a different commit to make a process look tidier. If a release
   was built from a commit, the tag belongs on that commit, even when a later one
   is better. The gate fix did not need to be in the tag; it needed to be on
   `main`, and it was.
4. **An unexplained tag in a release repository is an incident, not an oddity.** A
   tag push is a publish trigger. Establish where it came from before deciding
   what to do about it.

## Where the tag came from, and the limits of finding out

**Not established, and the reason is worth recording.**

Ruled out: no `push.followTags` or `remote.origin.push` is configured in any
clone, local, global or system, so no ordinary branch push could have carried a
lightweight tag along; and every push in the session that was running the release
used an explicit refspec.

Not available: the account is a **user account, not an organisation**, so there is
no audit log API. `/orgs/{login}/audit-log` does not apply and
`/users/{login}/audit-log` returns 404. The repository event stream records no tag
creation at all, including tag pushes that are known to have happened, so it
cannot answer the question either. Everything GitHub records is attributed to the
single account, which cannot distinguish one automated session from another.

Circumstantial: a second session was demonstrably working in this repository the
same hour, and opened two pull requests at 11:15 and 11:16 covering overlapping
release work. Both branch from commits made at 11:07 and 11:10, so they postdate
the tag and do not prove that session pushed it. It remains the most plausible
explanation and it is not a demonstrated one.

**The structural finding: with a single shared account and no audit log, this
estate cannot attribute a write to a session.** Every automated actor is the same
login. That was tolerable while one session ran at a time. It is not tolerable for
a release repository, where a tag push publishes.

This estate sells attribution and cannot currently attribute its own releases.

Worth considering: a distinct machine account or token per session so that
attribution exists at all, and a check that refuses a release tag whose commit is
not the tip of `main` at push time.

## Related

* `docs/findings/why-0-9-0-and-not-1-0-0.md`, the version decision for this release.
* `GHSA-p336-fc9m-vcq4`, the advisory this release fixes.
* The resolvability gate fix, PR #97, which is the change the cancellation was
  trying to sequence before the publish.
* Issue #103, the shared-identity problem this incident exposed, with both
  proposals: per-session identity, and a check that refuses a release tag whose
  commit is not the tip of `main`.
