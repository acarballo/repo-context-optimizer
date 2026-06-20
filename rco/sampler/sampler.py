"""Sampler: selects files based on different strategies within a token budget."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from rco.analyzer.category_detector import CategorizedFile, Category
from rco.analyzer.token_counter import FileTokenInfo

if TYPE_CHECKING:
    pass


class Strategy(str, Enum):
    CATEGORY = "category"       # N files per category (diverse coverage)
    CENTRALITY = "centrality"   # Most-imported files first
    BUDGET = "budget"           # Best mix within token budget (default)
    RANDOM = "random"           # Stratified random sample


@dataclass
class SampledFile:
    categorized: CategorizedFile
    token_info: FileTokenInfo
    centrality: float
    selection_reason: str

    @property
    def relative_path(self) -> str:
        return self.categorized.relative_path

    @property
    def tokens(self) -> int:
        return self.token_info.tokens

    @property
    def category(self) -> Category:
        return self.categorized.category

    @property
    def language(self) -> str:
        return self.categorized.language


@dataclass
class SampleResult:
    files: list[SampledFile]
    total_tokens: int
    budget: int
    strategy: Strategy

    @property
    def utilization(self) -> float:
        return self.total_tokens / self.budget if self.budget else 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_enriched(
    categorized: list[CategorizedFile],
    token_map: dict[str, FileTokenInfo],
    centrality_map: dict[str, float],
) -> list[SampledFile]:
    result = []
    for cf in categorized:
        ti = token_map.get(cf.relative_path)
        if ti is None:
            continue
        result.append(SampledFile(
            categorized=cf,
            token_info=ti,
            centrality=centrality_map.get(cf.relative_path, 0.0),
            selection_reason="",
        ))
    return result


def _fits_in_budget(selected: list[SampledFile], candidate: SampledFile, budget: int) -> bool:
    used = sum(f.tokens for f in selected)
    return used + candidate.tokens <= budget


# ---------------------------------------------------------------------------
# Sampling strategies
# ---------------------------------------------------------------------------

def _sample_category(
    enriched: list[SampledFile],
    budget: int,
    per_category: int,
) -> list[SampledFile]:
    """Pick up to *per_category* files from each category, ordered by centrality."""
    by_cat: dict[Category, list[SampledFile]] = {}
    for f in enriched:
        by_cat.setdefault(f.category, []).append(f)

    # Within each category, sort by centrality desc
    for cat in by_cat:
        by_cat[cat].sort(key=lambda f: f.centrality, reverse=True)

    # Round-robin across categories so we get diversity
    selected: list[SampledFile] = []
    categories = list(by_cat.keys())
    indices = {cat: 0 for cat in categories}

    round_n = 0
    while round_n < per_category:
        added_this_round = False
        for cat in categories:
            idx = indices[cat]
            pool = by_cat[cat]
            while idx < len(pool):
                candidate = pool[idx]
                idx += 1
                if _fits_in_budget(selected, candidate, budget):
                    candidate.selection_reason = f"category:{cat.value} rank:{idx}"
                    selected.append(candidate)
                    added_this_round = True
                    break
            indices[cat] = idx
        if not added_this_round:
            break
        round_n += 1

    return selected


def _sample_centrality(
    enriched: list[SampledFile],
    budget: int,
    top_n: int,
) -> list[SampledFile]:
    """Pick the most-imported files first until budget is exhausted."""
    ranked = sorted(enriched, key=lambda f: f.centrality, reverse=True)
    selected: list[SampledFile] = []
    for i, candidate in enumerate(ranked):
        if len(selected) >= top_n:
            break
        if _fits_in_budget(selected, candidate, budget):
            candidate.selection_reason = f"centrality:{candidate.centrality:.2f} rank:{i+1}"
            selected.append(candidate)
    return selected


def _sample_budget(
    enriched: list[SampledFile],
    budget: int,
) -> list[SampledFile]:
    """
    Greedy knapsack: score = 0.6*centrality + 0.4*(1 - normalized_tokens).
    Balances relevance with token efficiency.
    Ensures at least one file per detected category when possible.
    """
    max_tokens = max((f.tokens for f in enriched), default=1)

    def score(f: SampledFile) -> float:
        token_penalty = f.tokens / max_tokens
        return 0.6 * f.centrality + 0.4 * (1.0 - token_penalty)

    ranked = sorted(enriched, key=score, reverse=True)

    # First pass: one file per category
    selected: list[SampledFile] = []
    covered: set[Category] = set()
    remaining: list[SampledFile] = []

    for f in ranked:
        if f.category not in covered and _fits_in_budget(selected, f, budget):
            f.selection_reason = f"budget:first-of-{f.category.value} score:{score(f):.2f}"
            selected.append(f)
            covered.add(f.category)
        else:
            remaining.append(f)

    # Second pass: fill remaining budget
    for f in remaining:
        if _fits_in_budget(selected, f, budget):
            f.selection_reason = f"budget:fill score:{score(f):.2f}"
            selected.append(f)

    return selected


def _sample_random(
    enriched: list[SampledFile],
    budget: int,
    seed: int | None = None,
) -> list[SampledFile]:
    """Stratified random sample: picks randomly within each category."""
    rng = random.Random(seed)
    by_cat: dict[Category, list[SampledFile]] = {}
    for f in enriched:
        by_cat.setdefault(f.category, []).append(f)

    pool: list[SampledFile] = []
    for cat_files in by_cat.values():
        rng.shuffle(cat_files)
        pool.extend(cat_files)

    selected: list[SampledFile] = []
    for f in pool:
        if _fits_in_budget(selected, f, budget):
            f.selection_reason = f"random:stratified category:{f.category.value}"
            selected.append(f)
    return selected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sample(
    categorized: list[CategorizedFile],
    token_map: dict[str, FileTokenInfo],
    centrality_map: dict[str, float],
    strategy: Strategy = Strategy.BUDGET,
    budget: int = 100_000,
    per_category: int = 3,
    top_n: int = 30,
    exclude_categories: list[Category] | None = None,
    exclude_tests: bool = False,
    seed: int | None = None,
) -> SampleResult:
    """
    Select files according to *strategy* within *budget* tokens.

    Args:
        categorized:       Output of category_detector.detect_all().
        token_map:         Dict[relative_path → FileTokenInfo].
        centrality_map:    Dict[relative_path → float] from dependency_graph.
        strategy:          Sampling strategy to use.
        budget:            Maximum tokens in the output context.
        per_category:      (category strategy) Files per category.
        top_n:             (centrality strategy) Max files to select.
        exclude_categories: Categories to skip entirely.
        exclude_tests:     Shortcut to exclude test files.
        seed:              Random seed for reproducibility (random strategy).
    """
    excluded = set(exclude_categories or [])
    if exclude_tests:
        excluded.add(Category.TEST)

    filtered = [cf for cf in categorized if cf.category not in excluded]
    enriched = _build_enriched(filtered, token_map, centrality_map)

    if strategy == Strategy.CATEGORY:
        files = _sample_category(enriched, budget, per_category)
    elif strategy == Strategy.CENTRALITY:
        files = _sample_centrality(enriched, budget, top_n)
    elif strategy == Strategy.RANDOM:
        files = _sample_random(enriched, budget, seed)
    else:  # BUDGET (default)
        files = _sample_budget(enriched, budget)

    total = sum(f.tokens for f in files)
    return SampleResult(files=files, total_tokens=total, budget=budget, strategy=strategy)
