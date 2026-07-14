#!/usr/bin/env python3
"""Check candidate Markdown links, including GitHub-style local anchors.

"Candidate" means every existing file in the index plus non-ignored untracked
files.  That deliberately checks newly drafted release documentation before it is
staged, without misreporting those files as already tracked. Markdown copied into a
frozen baseline is release evidence rather than current documentation: its exact
tag bytes are checked by ``check_released_baselines.py`` and are not link-rewritten.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^\s)]+)(?:\s+['\"][^'\"]*['\"])?\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
ATX_HEADING = re.compile(r"^[ ]{0,3}#{1,6}(?:[ \t]+|$)(?P<text>.*)$")
SETEXT_HEADING = re.compile(r"^[ ]{0,3}(?:=+|-+)[ \t]*$")
FENCE_OPEN = re.compile(r"^[ ]{0,3}(?P<marker>`{3,}|~{3,})")
HTML_TAG = re.compile(r"<[A-Za-z][^>]*>")
HTML_ANCHOR_ATTR = re.compile(
    r"\b(?:id|name)\s*=\s*(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
INLINE_LINK_TEXT = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
REFERENCE_LINK_TEXT = re.compile(r"!?\[([^\]]*)\]\[[^\]]*\]")
CODE_SPAN = re.compile(r"(`+)(.*?)\1")
# This is the punctuation range used by github-slugger. Underscore and hyphen are
# intentionally retained; whitespace becomes one hyphen per character.
GITHUB_PUNCTUATION = re.compile(
    r"[\u2000-\u206F\u2E00-\u2E7F\\'!\"#$%&()*+,./:;<=>?@\[\]^`{|}~]"
)
FROZEN_RELEASED_BASELINE_PREFIXES = tuple(
    f"conformance/baseline/{tag}/"
    for tag in ("v0.5.0", "v0.6.0", "v0.7.0", "v0.8.0")
)


def candidate_files(repo: Path = REPO) -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo,
    ).decode("utf-8", errors="strict")
    return {
        name
        for name in output.split("\0")
        if name and (repo / name).is_file()
    }


def candidate_markdown(candidates: set[str]) -> list[str]:
    return sorted(
        name
        for name in candidates
        if name.lower().endswith(".md")
        and not name.startswith(FROZEN_RELEASED_BASELINE_PREFIXES)
    )


def _heading_text(text: str) -> str:
    # ATX closing hashes are syntax only when preceded by whitespace.
    text = re.sub(r"[ \t]+#+[ \t]*$", "", text)
    text = INLINE_LINK_TEXT.sub(lambda match: match.group(1), text)
    text = REFERENCE_LINK_TEXT.sub(lambda match: match.group(1), text)
    text = CODE_SPAN.sub(lambda match: match.group(2), text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\([\\`*{}\[\]()#+.!_>-])", r"\1", text)
    return html.unescape(text).strip()


def github_slug(text: str) -> str:
    slug = GITHUB_PUNCTUATION.sub("", _heading_text(text).lower())
    return re.sub(r"\s", "-", slug)


def _unique_slug(base: str, seen: dict[str, int]) -> str:
    if base not in seen:
        seen[base] = 0
        return base
    suffix = seen[base] + 1
    candidate = f"{base}-{suffix}"
    while candidate in seen:
        suffix += 1
        candidate = f"{base}-{suffix}"
    seen[base] = suffix
    seen[candidate] = 0
    return candidate


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    slugs: dict[str, int] = {}
    fence: tuple[str, int] | None = None
    prior_text: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if fence is None:
            match = FENCE_OPEN.match(line)
            if match:
                marker = match.group("marker")
                fence = (marker[0], len(marker))
                prior_text = None
                continue
        else:
            character, minimum = fence
            if re.fullmatch(rf"[ ]{{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", line):
                fence = None
            continue

        for tag in HTML_TAG.finditer(line):
            for match in HTML_ANCHOR_ATTR.finditer(tag.group(0)):
                anchor = match.group("double") or match.group("single") or match.group("bare")
                anchors.add(html.unescape(anchor))

        atx = ATX_HEADING.match(line)
        if atx:
            base = github_slug(atx.group("text"))
            if base:
                anchors.add(_unique_slug(base, slugs))
            prior_text = None
            continue

        if prior_text is not None and SETEXT_HEADING.fullmatch(line):
            base = github_slug(prior_text)
            if base:
                anchors.add(_unique_slug(base, slugs))
            prior_text = None
            continue

        stripped = line.strip()
        prior_text = stripped if stripped else None

    return anchors


def check_links(repo: Path, candidates: set[str]) -> list[str]:
    repo = repo.resolve()
    markdown = candidate_markdown(candidates)
    anchor_cache: dict[str, set[str]] = {}
    failures: list[str] = []
    for name in markdown:
        path = repo / name
        fenced = False
        fence_marker: tuple[str, int] | None = None
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if fence_marker is None:
                opening = FENCE_OPEN.match(line)
                if opening:
                    marker = opening.group("marker")
                    fence_marker = (marker[0], len(marker))
                    fenced = True
                    continue
            else:
                character, minimum = fence_marker
                if re.fullmatch(
                    rf"[ ]{{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", line
                ):
                    fence_marker = None
                    fenced = False
                continue
            if fenced:
                continue

            for match in LINK.finditer(line):
                raw = match.group("target")
                if raw.startswith("<") and raw.endswith(">"):
                    raw = raw[1:-1]
                if not raw or raw.startswith("/") or SCHEME.match(raw):
                    continue

                before_fragment, separator, raw_fragment = raw.partition("#")
                raw_path = before_fragment.split("?", 1)[0]
                relative = urllib.parse.unquote(raw_path)
                fragment = urllib.parse.unquote(raw_fragment) if separator else ""

                if relative:
                    target = (path.parent / relative).resolve()
                else:
                    target = path.resolve()
                try:
                    repo_relative = target.relative_to(repo).as_posix()
                except ValueError:
                    failures.append(f"{name}:{number}: target escapes repository: {raw}")
                    continue

                target_exists = repo_relative in candidates or any(
                    candidate.startswith(repo_relative.rstrip("/") + "/")
                    for candidate in candidates
                )
                if not target_exists:
                    failures.append(f"{name}:{number}: missing candidate target: {raw}")
                    continue

                if not fragment or target.suffix.lower() != ".md" or not target.is_file():
                    continue
                if repo_relative not in anchor_cache:
                    anchor_cache[repo_relative] = markdown_anchors(target)
                if fragment not in anchor_cache[repo_relative]:
                    failures.append(
                        f"{name}:{number}: missing Markdown anchor #{fragment} in {repo_relative}"
                    )
    return failures


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ncp-markdown-links-") as directory:
        root = Path(directory)
        first = root / "first.md"
        second = root / "second.md"
        first.write_text(
            """# First heading

## Repeat
## Repeat
## Repeat-1
## Repeat

Setext title
============

<a id="manual-anchor"></a>

[same](#first-heading)
[duplicate](#repeat-1)
[collision](#repeat-1-1)
[later duplicate](#repeat-2)
[setext](#setext-title)
[explicit](#manual-anchor)
[cross](second.md#target--punctuation)
""",
            encoding="utf-8",
        )
        second.write_text(
            """# Target & punctuation!

```text
# not-a-heading
```
""",
            encoding="utf-8",
        )
        frozen = root / "conformance" / "baseline" / "v0.5.0" / "README.md"
        frozen.parent.mkdir(parents=True)
        frozen.write_text("[historical dead link](missing.md)\n", encoding="utf-8")
        candidates = {
            "first.md",
            "second.md",
            "conformance/baseline/v0.5.0/README.md",
        }
        assert check_links(root, candidates) == []

        first.write_text(first.read_text(encoding="utf-8") + "[bad](#not-a-heading)\n")
        failures = check_links(root, candidates)
        assert len(failures) == 1 and "missing Markdown anchor" in failures[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test", action="store_true", help="run focused anchor/link regressions"
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()

    candidates = candidate_files()
    markdown = candidate_markdown(candidates)
    failures = check_links(REPO, candidates)
    if failures:
        print("Markdown candidate-link gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(
        f"OK: {len(markdown)} candidate Markdown files have valid "
        "candidate-relative targets and anchors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
