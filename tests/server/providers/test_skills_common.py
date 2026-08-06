"""Tests for skills frontmatter parsing."""

from __future__ import annotations

import pytest

from fastmcp.server.providers.skills._common import parse_frontmatter


class TestParseFrontmatter:
    def test_single_line_description(self):
        content = "---\ndescription: A simple description\n---\n# Body"
        frontmatter, remaining = parse_frontmatter(content)
        assert frontmatter["description"] == "A simple description"
        assert "# Body" in remaining

    def test_multiline_description_pipe(self):
        content = "---\ndescription: |\n  First line.\n  Second line.\n---\n# Body"
        frontmatter, remaining = parse_frontmatter(content)
        assert "First line." in frontmatter["description"]
        assert "Second line." in frontmatter["description"]

    def test_multiline_description_folded(self):
        content = "---\ndescription: >\n  First line.\n  Second line.\n---\n# Body"
        frontmatter, remaining = parse_frontmatter(content)
        assert frontmatter["description"] != ""

    def test_no_type_coercion_yes(self):
        content = "---\ndescription: yes\n---\n"
        frontmatter, _ = parse_frontmatter(content)
        assert frontmatter["description"] == "yes"
        assert isinstance(frontmatter["description"], str)

    def test_no_type_coercion_true(self):
        content = "---\ndescription: true\n---\n"
        frontmatter, _ = parse_frontmatter(content)
        assert frontmatter["description"] == "true"
        assert isinstance(frontmatter["description"], str)

    def test_no_type_coercion_float(self):
        content = "---\nversion: 1.10\n---\n"
        frontmatter, _ = parse_frontmatter(content)
        assert frontmatter["version"] == "1.10"
        assert isinstance(frontmatter["version"], str)

    def test_other_keys_preserved(self):
        content = "---\nname: my-skill\nauthor: sai\n---\n"
        frontmatter, _ = parse_frontmatter(content)
        assert frontmatter["name"] == "my-skill"
        assert frontmatter["author"] == "sai"

    def test_malformed_yaml_falls_back(self):
        content = "---\ndescription: value: with: colons\n---\n"
        frontmatter, _ = parse_frontmatter(content)
        assert "description" in frontmatter

    def test_no_frontmatter_returns_empty(self):
        content = "# Just markdown\nNo frontmatter here."
        frontmatter, remaining = parse_frontmatter(content)
        assert frontmatter == {}
        assert remaining == content

    def test_empty_frontmatter_returns_empty_dict(self):
        content = "---\n---\n# Body"
        frontmatter, remaining = parse_frontmatter(content)
        assert frontmatter == {}