---
name: release
description: Cut a FastMCP release end to end. Use when the maintainer says "cut a release", "prep a patch", "ship 4.x.y", or asks what a release would contain. Covers the notes preview, the title pun, the docs changelog PR that must land before the tag, the tag itself, the publish chain, and verifying gofastmcp.com actually deployed.
---

# Cutting a release

A release is a tag on the branch that owns the line (`main` for the current major,
`release/3.x` for 3.x maintenance). Tagging triggers `Publish fastmcp-slim to PyPI`,
which chains into `fastmcp-tasks`, `fastmcp-remote`, and `fastmcp`; the `fastmcp`
publish job then opens the `published-docs` PR that makes gofastmcp.com reflect the
release. Two hand-maintained docs files mirror every release and must be on the
tagged commit, so the docs PR always lands first.

## Procedure

1. **Preview what's in it.**

   ```bash
   git fetch origin && git log v<prev>..origin/main --format='%h %s'
   gh api -X POST repos/PrefectHQ/fastmcp/releases/generate-notes \
     -f tag_name=v<new> -f target_commitish=main -f previous_tag_name=v<prev> --jq .body
   ```

   Read the previous two releases for voice: `gh release list -L 5`, `gh release view <tag>`.

2. **Propose titles.** Titles are `v<version>: <pun>`, pun on the release's main
   theme. Offer several; the maintainer picks. Draft the handwritten notes at the
   same time: one or two sentences for a patch, narrative prose for a point release.
   Get sign-off on both before anything is pushed.

3. **Write the notes file** to the scratchpad (intro only, no title; the release
   title is the heading).

4. **Docs entries.** Branch from `origin/main`, render both blocks, and insert each
   above the newest existing `<Update ...>` in `docs/changelog.mdx` and
   `docs/updates.mdx`:

   ```bash
   uv run .claude/skills/release/changelog_entry.py v<new> v<prev> "<pun>" notes.md
   ```

   Then run Mintlify's parser before pushing:

   ```bash
   cd docs && npx --yes mint@latest broken-links
   ```

   Open the PR (`docs: add v<new> changelog entries`) and merge it. Branch policy
   needs `--admin` on a maintainer-driven release.

5. **Tag**, immediately after the docs PR merges, from the same branch:

   ```bash
   gh release create v<new> --target main --title "v<new>: <pun>" \
     --generate-notes --notes-start-tag v<prev> --notes-file notes.md
   ```

   Maintenance lines use `--target release/3.x` and the branch's own last tag.
   The compare link at the bottom of the created release must read `v<prev>...v<new>`.

6. **Watch the chain.** `gh run watch` the slim publish, then the `fastmcp` publish
   (`gh run list --workflow "Publish fastmcp to PyPI"`). Confirm each package with
   `curl -s https://pypi.org/pypi/<pkg>/<new>/json | jq .info.version`; the
   unversioned endpoint lags a few minutes.

7. **Publish docs.** The `fastmcp` publish job opens `Publish FastMCP v<new> docs`
   against `published-docs`. Merge it with `--merge --admin`. Then check Mintlify's
   verdict on the new tip, which is the only signal that the deploy happened:

   ```bash
   sha=$(git rev-parse origin/published-docs)
   gh api repos/PrefectHQ/fastmcp/commits/$sha/check-runs \
     --jq '.check_runs[] | select(.name=="Mintlify Deployment") | .conclusion, .output.text'
   ```

   Verify pages through their markdown endpoints, which bypass the HTML edge cache:
   `curl -s https://gofastmcp.com/changelog.md | grep -c "<pun>"`, same for
   `updates.md` and any page the release touched.

## Template: notes.md for a patch

```
`ClientGroup` now reference-counts its context the way `Client` does, so entering a
connected group from a nested block or a concurrent task reuses the existing
connections instead of raising.
```

## Gotchas

- Mintlify persists its per-file hashes even when a deploy fails on a parse error.
  The next successful deploy only rebuilds files changed since the failure. After
  fixing a parse error, make a content change to every path the failed run listed
  under "Updating targeted paths" and publish again.
- `--generate-notes` copies PR titles verbatim; a title containing `<1`, `{`, or `}`
  breaks MDX. `changelog_entry.py` wraps those in backticks; check the output anyway.
- Without `--notes-start-tag`, a prerelease tag becomes the changelog start and the
  PR list is silently truncated.
- Maintenance releases publish packages and notes but never repoint `published-docs`;
  their changelog entries go on the maintenance branch under the matching major section.

## Check before finishing

Three curls return non-zero: `pypi.org/pypi/fastmcp/<new>/json`,
`gofastmcp.com/changelog.md | grep -c "<pun>"`, and `gofastmcp.com/updates.md | grep -c "<pun>"`.
