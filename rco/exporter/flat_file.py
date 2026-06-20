"""Flat file exporter: generates a single Markdown context file for LLMs."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from rco.sampler.sampler import SampleResult


_LANG_MAP = {
    "java": "java",
    "kotlin": "kotlin",
    "javascript": "javascript",
    "typescript": "typescript",
    "python": "python",
    "go": "go",
    "rust": "rust",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "json": "json",
    "yaml": "yaml",
    "toml": "toml",
    "xml": "xml",
    "markdown": "markdown",
    "unknown": "",
}


def _strip_comments(text: str, language: str) -> str:
    """
    Lightly strip comments to reduce token count.
    Only removes block comments and standalone comment lines.
    Preserves JSDoc / Javadoc as they convey API intent.
    """
    if language in ("java", "kotlin", "javascript", "typescript", "go", "rust", "csharp"):
        # Remove single-line comments that are the entire line
        text = re.sub(r"^\s*//(?!\/).*$", "", text, flags=re.MULTILINE)
        # Remove /* ... */ block comments but NOT /** ... */ (Javadoc/JSDoc)
        text = re.sub(r"/\*(?!\*).*?\*/", "", text, flags=re.DOTALL)
    elif language == "python":
        text = re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)
    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def export(
    result: SampleResult,
    output_path: str | Path,
    repo_name: str = "repository",
    compress: bool = False,
) -> Path:
    """
    Write a Markdown context file from a SampleResult.

    Args:
        result:      Output of sampler.sample().
        output_path: Destination .md or .txt file.
        repo_name:   Human-readable repo name used in the header.
        compress:    If True, strip comments to save tokens.

    Returns:
        Resolved path to the written file.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = result.total_files if hasattr(result, "total_files") else len(result.files)

    lines: list[str] = [
        f"# Repo Context — {repo_name}",
        f"> Generated: {now}  |  "
        f"Files: {len(result.files)}  |  "
        f"Tokens: {result.total_tokens:,} / {result.budget:,}  |  "
        f"Budget used: {result.utilization:.1%}  |  "
        f"Strategy: {result.strategy.value}",
        "",
    ]

    # Summary table
    lines += [
        "## Selected files",
        "",
        "| # | File | Category | Language | Tokens | Centrality |",
        "|---|------|----------|----------|--------|------------|",
    ]
    for i, sf in enumerate(result.files, 1):
        lines.append(
            f"| {i} | `{sf.relative_path}` | {sf.category.value} "
            f"| {sf.language} | {sf.tokens:,} | {sf.centrality:.2f} |"
        )

    lines += ["", "---", ""]

    # File contents
    for i, sf in enumerate(result.files, 1):
        lang_tag = _LANG_MAP.get(sf.language, "")
        text = sf.categorized.scanned_file.read_text()

        if compress:
            text = _strip_comments(text, sf.language)

        lines += [
            f"## [{i}/{len(result.files)}] {sf.relative_path}",
            f"> **Category:** {sf.category.value}  |  "
            f"**Tokens:** {sf.tokens:,}  |  "
            f"**Centrality:** {sf.centrality:.2f}  |  "
            f"**Reason:** {sf.selection_reason}",
            "",
            f"```{lang_tag}",
            text,
            "```",
            "",
            "---",
            "",
        ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
