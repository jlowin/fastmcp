"""Render docs/changelog.mdx and docs/updates.mdx blocks for a release.

Usage:
    uv run .claude/skills/release/changelog_entry.py v4.0.1 v4.0.0 "Come Back Any Time" notes.md

Reads the maintainer-approved notes file for the intro paragraph and pulls the
PR list from GitHub's generate-notes API, so the docs entry matches what
`gh release create --generate-notes` will append.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys

REPO = "PrefectHQ/fastmcp"


def generate_notes(tag: str, previous: str, target: str) -> str:
    out = subprocess.check_output(
        [
            "gh",
            "api",
            "-X",
            "POST",
            f"repos/{REPO}/releases/generate-notes",
            "-f",
            f"tag_name={tag}",
            "-f",
            f"target_commitish={target}",
            "-f",
            f"previous_tag_name={previous}",
            "--jq",
            ".body",
        ],
        text=True,
    )
    return out


def linkify(body: str) -> str:
    body = re.sub(r"<!--.*?-->\n?", "", body, flags=re.S)
    body = body.replace("## What's Changed\n", "")
    body = re.sub(
        r"by @([\w-]+) in https://github\.com/" + re.escape(REPO) + r"/pull/(\d+)",
        r"by [@\1](https://github.com/\1) in [#\2](https://github.com/"
        + REPO
        + r"/pull/\2)",
        body,
    )
    body = re.sub(
        r"\* @([\w-]+) made their first contribution in https://github\.com/"
        + re.escape(REPO)
        + r"/pull/(\d+)",
        r"* @\1 made their first contribution in [#\2](https://github.com/"
        + REPO
        + r"/pull/\2)",
        body,
    )
    body = re.sub(
        r"\*\*Full Changelog\*\*: https://github\.com/"
        + re.escape(REPO)
        + r"/compare/(\S+)",
        r"**Full Changelog**: [\1](https://github.com/" + REPO + r"/compare/\1)",
        body,
    )
    return body.strip()


def escape_mdx(text: str) -> str:
    """Backtick-wrap bare `<digit`, `{`, `}` outside code spans; MDX reads them as JSX."""

    def fix(line: str) -> str:
        parts = line.split("`")
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"(<\d[^\s`]*)", r"`\1`", parts[i])
            parts[i] = re.sub(r"(\{[^}]*\})", r"`\1`", parts[i])
        return "`".join(parts)

    return "\n".join(fix(line) for line in text.splitlines())


def main() -> None:
    tag, previous, pun, notes_path = sys.argv[1:5]
    target = sys.argv[5] if len(sys.argv) > 5 else "main"
    version = tag.lstrip("v")
    today = dt.date.today()
    intro = open(notes_path).read().strip()
    body = escape_mdx(linkify(generate_notes(tag, previous, target)))
    url = f"https://github.com/{REPO}/releases/tag/{tag}"

    changelog = f'''<Update label="{tag}" description="{today.isoformat()}">

**[{tag}: {pun}]({url})**

{intro}

{body}

</Update>
'''
    updates = f'''<Update label="FastMCP {version}" description="{today.strftime("%B %-d, %Y")}" tags={{["Releases"]}}>
<Card
title="FastMCP {tag}: {pun}"
href="{url}"
cta="Read the release notes"
>
{intro.splitlines()[0]}
</Card>
</Update>
'''
    print(json.dumps({"changelog": changelog, "updates": updates}))


if __name__ == "__main__":
    main()
