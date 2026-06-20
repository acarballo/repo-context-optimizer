"""Dependency graph: builds an import graph and computes file centrality scores."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rco.scanner.file_scanner import ScannedFile, ScanResult


@dataclass
class DependencyGraph:
    """
    Directed graph where an edge A → B means "file A imports file B".
    Centrality = in-degree (how many files import this file), normalized 0-1.
    """
    _edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    _all_nodes: set[str] = field(default_factory=set)

    def add_edge(self, importer: str, imported: str) -> None:
        self._edges[importer].add(imported)
        self._all_nodes.add(importer)
        self._all_nodes.add(imported)

    def in_degree(self, node: str) -> int:
        return sum(1 for targets in self._edges.values() if node in targets)

    def centrality_scores(self) -> dict[str, float]:
        """Return normalized in-degree scores (0.0–1.0) for all nodes."""
        scores = {node: self.in_degree(node) for node in self._all_nodes}
        max_score = max(scores.values(), default=1)
        if max_score == 0:
            return {k: 0.0 for k in scores}
        return {k: v / max_score for k, v in scores.items()}


# ---------------------------------------------------------------------------
# Import extractors per language
# ---------------------------------------------------------------------------

def _extract_java_imports(text: str) -> list[str]:
    """Extract class names from Java import statements."""
    return re.findall(r"^import\s+(?:static\s+)?[\w.]+\.(\w+);", text, re.MULTILINE)


def _extract_js_ts_imports(text: str) -> list[str]:
    """Extract module paths from JS/TS import/require statements."""
    # import ... from '...'  or  require('...')
    patterns = [
        r'from\s+[\'"]([^\'"\s]+)[\'"]',
        r'require\s*\(\s*[\'"]([^\'"\s]+)[\'"]\s*\)',
        r'import\s*\(\s*[\'"]([^\'"\s]+)[\'"]\s*\)',  # dynamic import
    ]
    results = []
    for p in patterns:
        results.extend(re.findall(p, text))
    return results


def _resolve_js_import(importer_path: str, import_path: str, root: Path,
                        all_relative_paths: set[str]) -> str | None:
    """Try to resolve a relative JS/TS import path to a known file."""
    if not import_path.startswith("."):
        return None  # external package — skip

    importer_dir = Path(importer_path).parent
    candidate = (importer_dir / import_path).as_posix()

    # Try with common extensions
    for ext in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
        attempt = candidate + ext
        if attempt in all_relative_paths:
            return attempt

    return None


def build(scan_result: ScanResult) -> DependencyGraph:
    """Build a dependency graph from import analysis of all scanned files."""
    graph = DependencyGraph()
    all_paths = {f.relative_path for f in scan_result.files}

    # Index Java class names → relative path for resolution
    java_class_index: dict[str, str] = {}
    for sf in scan_result.files:
        if sf.language == "java":
            class_name = Path(sf.relative_path).stem
            java_class_index[class_name] = sf.relative_path

    for sf in scan_result.files:
        text = sf.read_text()
        importer = sf.relative_path

        if sf.language == "java":
            for class_name in _extract_java_imports(text):
                if class_name in java_class_index:
                    imported = java_class_index[class_name]
                    if imported != importer:
                        graph.add_edge(importer, imported)

        elif sf.language in ("javascript", "typescript"):
            for import_path in _extract_js_ts_imports(text):
                resolved = _resolve_js_import(importer, import_path,
                                               scan_result.root, all_paths)
                if resolved and resolved != importer:
                    graph.add_edge(importer, resolved)

    return graph
