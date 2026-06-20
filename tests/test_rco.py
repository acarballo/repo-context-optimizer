"""Basic tests for repo-context-optimizer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo with Java and TS files."""
    # Java files
    (tmp_path / "src/main/java/com/app").mkdir(parents=True)
    (tmp_path / "src/main/java/com/app/UserController.java").write_text(
        '@RestController\npublic class UserController {\n    @GetMapping("/users")\n'
        '    public List<User> list() { return service.findAll(); }\n}\n'
    )
    (tmp_path / "src/main/java/com/app/UserService.java").write_text(
        '@Service\npublic class UserService {\n    private final UserRepository repo;\n'
        '    public List<User> findAll() { return repo.findAll(); }\n}\n'
    )
    (tmp_path / "src/main/java/com/app/UserRepository.java").write_text(
        '@Repository\npublic interface UserRepository extends JpaRepository<User, Long> {}\n'
    )

    # TS files
    (tmp_path / "frontend/src/services").mkdir(parents=True)
    (tmp_path / "frontend/src/components").mkdir(parents=True)
    (tmp_path / "frontend/src/hooks").mkdir(parents=True)
    (tmp_path / "frontend/src/services/auth.service.ts").write_text(
        "import { Injectable } from '@angular/core';\n"
        "export class AuthService {\n  login() {}\n}\n"
    )
    (tmp_path / "frontend/src/components/Button.tsx").write_text(
        "import React from 'react';\nexport const Button = () => <button>Click</button>;\n"
    )
    (tmp_path / "frontend/src/hooks/useAuth.ts").write_text(
        "import { useState } from 'react';\nexport const useAuth = () => { return {}; };\n"
    )

    # Test file
    (tmp_path / "src/test/java/com/app").mkdir(parents=True)
    (tmp_path / "src/test/java/com/app/UserControllerTest.java").write_text(
        "public class UserControllerTest {\n  @Test\n  void test() {}\n}\n"
    )

    # .gitignore
    (tmp_path / ".gitignore").write_text("target/\nnode_modules/\n*.class\n")

    return tmp_path


# ---------------------------------------------------------------------------
# Scanner tests
# ---------------------------------------------------------------------------

class TestFileScanner:
    def test_scans_source_files(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        result = scan(sample_repo)
        paths = {f.relative_path.replace("\\", "/") for f in result.files}
        assert any("UserController.java" in p for p in paths)
        assert any("auth.service.ts" in p for p in paths)

    def test_excludes_gitignore(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        # Create a file that should be ignored
        target = sample_repo / "target"
        target.mkdir()
        (target / "App.class").write_text("binary")
        result = scan(sample_repo)
        paths = {f.relative_path for f in result.files}
        assert not any("target" in p for p in paths)

    def test_language_detection(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        result = scan(sample_repo)
        lang_map = {f.relative_path.replace("\\", "/"): f.language for f in result.files}
        java_files = [p for p in lang_map if p.endswith(".java")]
        assert all(lang_map[p] == "java" for p in java_files)
        ts_files = [p for p in lang_map if p.endswith(".ts") or p.endswith(".tsx")]
        assert all(lang_map[p] == "typescript" for p in ts_files)


# ---------------------------------------------------------------------------
# Category detector tests
# ---------------------------------------------------------------------------

class TestCategoryDetector:
    def test_java_controller(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.category_detector import detect_all, Category
        result = scan(sample_repo)
        categorized = detect_all(result.files)
        cat_map = {c.relative_path.replace("\\", "/"): c.category for c in categorized}
        controller = next(p for p in cat_map if "UserController.java" in p)
        assert cat_map[controller] == Category.CONTROLLER

    def test_java_service(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.category_detector import detect_all, Category
        result = scan(sample_repo)
        categorized = detect_all(result.files)
        cat_map = {c.relative_path.replace("\\", "/"): c.category for c in categorized}
        service = next(p for p in cat_map if "UserService.java" in p)
        assert cat_map[service] == Category.SERVICE

    def test_ts_hook(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.category_detector import detect_all, Category
        result = scan(sample_repo)
        categorized = detect_all(result.files)
        cat_map = {c.relative_path.replace("\\", "/"): c.category for c in categorized}
        hook = next(p for p in cat_map if "useAuth.ts" in p)
        assert cat_map[hook] == Category.HOOK

    def test_test_file_detected(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.category_detector import detect_all, Category
        result = scan(sample_repo)
        categorized = detect_all(result.files)
        cat_map = {c.relative_path.replace("\\", "/"): c.category for c in categorized}
        test = next(p for p in cat_map if "UserControllerTest" in p)
        assert cat_map[test] == Category.TEST


# ---------------------------------------------------------------------------
# Token counter tests
# ---------------------------------------------------------------------------

class TestTokenCounter:
    def test_counts_tokens(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.token_counter import analyze
        result = scan(sample_repo)
        report = analyze(result, model="claude")
        assert report.total_tokens > 0
        assert all(fi.tokens >= 0 for fi in report.file_tokens)

    def test_by_language(self, sample_repo: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.token_counter import analyze
        result = scan(sample_repo)
        report = analyze(result, model="claude")
        by_lang = report.by_language()
        assert "java" in by_lang
        assert "typescript" in by_lang


# ---------------------------------------------------------------------------
# Sampler tests
# ---------------------------------------------------------------------------

class TestSampler:
    def _setup(self, sample_repo: Path):
        from rco.scanner.file_scanner import scan
        from rco.analyzer.token_counter import analyze
        from rco.analyzer.category_detector import detect_all
        from rco.analyzer.dependency_graph import build
        scan_result = scan(sample_repo)
        token_report = analyze(scan_result, model="claude")
        categorized = detect_all(scan_result.files)
        graph = build(scan_result)
        centrality = graph.centrality_scores()
        token_map = {fi.relative_path: fi for fi in token_report.file_tokens}
        return categorized, token_map, centrality

    def test_budget_strategy_respects_budget(self, sample_repo: Path) -> None:
        from rco.sampler.sampler import sample, Strategy
        cat, tmap, cent = self._setup(sample_repo)
        result = sample(cat, tmap, cent, strategy=Strategy.BUDGET, budget=500)
        assert result.total_tokens <= 500

    def test_no_tests_excludes_tests(self, sample_repo: Path) -> None:
        from rco.sampler.sampler import sample, Strategy
        from rco.analyzer.category_detector import Category
        cat, tmap, cent = self._setup(sample_repo)
        result = sample(cat, tmap, cent, strategy=Strategy.BUDGET,
                        budget=200_000, exclude_tests=True)
        assert all(sf.category != Category.TEST for sf in result.files)


# ---------------------------------------------------------------------------
# Exporter tests
# ---------------------------------------------------------------------------

class TestExporter:
    def test_export_creates_file(self, sample_repo: Path, tmp_path: Path) -> None:
        from rco.scanner.file_scanner import scan
        from rco.analyzer.token_counter import analyze
        from rco.analyzer.category_detector import detect_all
        from rco.analyzer.dependency_graph import build
        from rco.sampler.sampler import sample, Strategy
        from rco.exporter.flat_file import export

        scan_result = scan(sample_repo)
        token_report = analyze(scan_result, model="claude")
        categorized = detect_all(scan_result.files)
        graph = build(scan_result)
        centrality = graph.centrality_scores()
        token_map = {fi.relative_path: fi for fi in token_report.file_tokens}

        result = sample(categorized, token_map, centrality,
                        strategy=Strategy.BUDGET, budget=200_000)
        out = tmp_path / "context.md"
        written = export(result, out, repo_name="test-repo")

        assert written.exists()
        content = written.read_text()
        assert "# Repo Context" in content
        assert "```java" in content or "```typescript" in content
