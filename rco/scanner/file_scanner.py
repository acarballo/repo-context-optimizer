"""File scanner: traverses a repo directory respecting .gitignore rules."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

# Folders always excluded regardless of .gitignore
ALWAYS_EXCLUDE_DIRS = {
    ".git", "node_modules", "target", "build", "dist",
    ".gradle", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    "coverage", ".nyc_output", "vendor", "venv", ".venv", "env",
}

# File extensions we consider source code
SOURCE_EXTENSIONS = {
    # JVM
    ".java", ".kt", ".groovy", ".scala",
    # JS / TS
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Web
    ".html", ".css", ".scss", ".less",
    # Config / data that is useful as context
    ".json", ".yaml", ".yml", ".toml", ".xml", ".properties",
    # Python
    ".py",
    # Other common languages
    ".go", ".rs", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    # Docs
    ".md", ".mdx",
}


@dataclass
class ScannedFile:
    path: Path
    relative_path: str
    extension: str
    size_bytes: int
    language: str = "unknown"

    def read_text(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


@dataclass
class ScanResult:
    root: Path
    files: list[ScannedFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    def by_language(self) -> dict[str, list[ScannedFile]]:
        result: dict[str, list[ScannedFile]] = {}
        for f in self.files:
            result.setdefault(f.language, []).append(f)
        return result


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gitignore = root / ".gitignore"
    if gitignore.exists():
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        return pathspec.PathSpec.from_lines("gitignore", lines)
    return None


def _detect_language(extension: str) -> str:
    mapping = {
        ".java": "java", ".kt": "kotlin", ".groovy": "groovy", ".scala": "scala",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".py": "python",
        ".go": "go", ".rs": "rust", ".rb": "ruby",
        ".php": "php", ".cs": "csharp", ".cpp": "cpp", ".c": "c",
        ".html": "html", ".css": "css", ".scss": "scss",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".xml": "xml", ".md": "markdown", ".mdx": "markdown",
    }
    return mapping.get(extension, "unknown")


def scan(root: str | Path, include_extensions: set[str] | None = None) -> ScanResult:
    """
    Recursively scan *root* and return a ScanResult with all source files found.

    Args:
        root: Repository root directory.
        include_extensions: Whitelist of extensions. Defaults to SOURCE_EXTENSIONS.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    extensions = include_extensions or SOURCE_EXTENSIONS
    gitignore = _load_gitignore(root)
    result = ScanResult(root=root)

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        # Prune excluded directories in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames
            if d not in ALWAYS_EXCLUDE_DIRS
            and not (gitignore and gitignore.match_file(
                str((current / d).relative_to(root)) + "/"
            ))
        ]

        for filename in filenames:
            file_path = current / filename
            ext = file_path.suffix.lower()

            if ext not in extensions:
                continue

            rel = str(file_path.relative_to(root))

            # Skip gitignored files
            if gitignore and gitignore.match_file(rel):
                continue

            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            result.files.append(
                ScannedFile(
                    path=file_path,
                    relative_path=rel,
                    extension=ext,
                    size_bytes=size,
                    language=_detect_language(ext),
                )
            )

    # Sort for deterministic output
    result.files.sort(key=lambda f: f.relative_path)
    return result
