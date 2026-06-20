"""CLI entry point for Repo Context Optimizer."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from rco import __version__

app = typer.Typer(
    name="rco",
    help="Repo Context Optimizer — prepare code repositories as LLM context.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        rprint(f"rco version [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True,
        help="Show version and exit."
    ),
) -> None:
    pass


# ---------------------------------------------------------------------------
# rco analyze
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    repo: Path = typer.Argument(..., help="Path to the repository root."),
    model: str = typer.Option("claude", "--model", "-m",
                               help="Token counting model: claude | gpt-4o | gpt-4 | gemini"),
    top: int = typer.Option(20, "--top", "-n", help="Number of heaviest files to show."),
    show_categories: bool = typer.Option(True, "--categories/--no-categories",
                                          help="Show category breakdown."),
) -> None:
    """
    [bold]Analyze[/bold] a repository: count tokens, detect file categories, show a summary.
    """
    from rco.scanner.file_scanner import scan
    from rco.analyzer.token_counter import analyze as count
    from rco.analyzer.category_detector import detect_all
    from rco.analyzer.dependency_graph import build as build_graph

    console.print(Panel(f"[bold cyan]Analyzing[/bold cyan] [white]{repo}[/white]",
                        box=box.ROUNDED))

    with console.status("Scanning files…"):
        scan_result = scan(repo)

    with console.status("Counting tokens…"):
        token_report = count(scan_result, model=model)

    with console.status("Detecting categories…"):
        categorized = detect_all(scan_result.files)

    with console.status("Building dependency graph…"):
        graph = build_graph(scan_result)
        centrality = graph.centrality_scores()

    # Summary panel
    console.print()
    console.print(Panel(
        f"[bold]Files scanned:[/bold] {scan_result.total_files}\n"
        f"[bold]Total size:[/bold]    {scan_result.total_bytes / 1024:.1f} KB\n"
        f"[bold]Total tokens:[/bold]  [yellow]{token_report.total_tokens:,}[/yellow]  "
        f"(model: {model})",
        title="[bold green]Summary[/bold green]",
        box=box.ROUNDED,
    ))

    # Language breakdown
    lang_table = Table(title="Tokens by language", box=box.SIMPLE)
    lang_table.add_column("Language", style="cyan")
    lang_table.add_column("Tokens", justify="right", style="yellow")
    lang_table.add_column("Files", justify="right")
    by_lang = token_report.by_language()
    lang_files = scan_result.by_language()
    for lang, tokens in by_lang.items():
        lang_table.add_row(lang, f"{tokens:,}", str(len(lang_files.get(lang, []))))
    console.print(lang_table)

    # Category breakdown
    if show_categories:
        cat_counts: dict[str, int] = {}
        for cf in categorized:
            cat_counts[cf.category.value] = cat_counts.get(cf.category.value, 0) + 1
        cat_table = Table(title="Files by category", box=box.SIMPLE)
        cat_table.add_column("Category", style="magenta")
        cat_table.add_column("Files", justify="right")
        for cat, count_ in sorted(cat_counts.items(), key=lambda x: -x[1]):
            cat_table.add_row(cat, str(count_))
        console.print(cat_table)

    # Top N heaviest files
    top_table = Table(title=f"Top {top} files by tokens", box=box.SIMPLE)
    top_table.add_column("#", justify="right", style="dim")
    top_table.add_column("File", style="white")
    top_table.add_column("Tokens", justify="right", style="yellow")
    top_table.add_column("Centrality", justify="right", style="cyan")
    for i, fi in enumerate(token_report.top_files(top), 1):
        c = centrality.get(fi.relative_path, 0.0)
        top_table.add_row(str(i), fi.relative_path, f"{fi.tokens:,}", f"{c:.2f}")
    console.print(top_table)


# ---------------------------------------------------------------------------
# rco sample
# ---------------------------------------------------------------------------

@app.command()
def sample(
    repo: Path = typer.Argument(..., help="Path to the repository root."),
    strategy: str = typer.Option("budget", "--strategy", "-s",
                                  help="budget | category | centrality | random"),
    budget: int = typer.Option(100_000, "--budget", "-b",
                                help="Max tokens in the output context."),
    per_category: int = typer.Option(3, "--per-category",
                                      help="(category strategy) Files per category."),
    top_n: int = typer.Option(30, "--top", help="(centrality strategy) Max files."),
    no_tests: bool = typer.Option(False, "--no-tests", help="Exclude test files."),
    model: str = typer.Option("claude", "--model", "-m", help="Tokenizer model family."),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed (random strategy)."),
) -> None:
    """
    [bold]Sample[/bold] files from a repository within a token budget and show the selection.
    """
    from rco.scanner.file_scanner import scan
    from rco.analyzer.token_counter import analyze as count
    from rco.analyzer.category_detector import detect_all
    from rco.analyzer.dependency_graph import build as build_graph
    from rco.sampler.sampler import sample as do_sample, Strategy

    console.print(Panel(
        f"[bold cyan]Sampling[/bold cyan] [white]{repo}[/white]  "
        f"strategy=[yellow]{strategy}[/yellow]  budget=[yellow]{budget:,}[/yellow] tokens",
        box=box.ROUNDED,
    ))

    with console.status("Scanning & analyzing…"):
        scan_result = scan(repo)
        token_report = count(scan_result, model=model)
        categorized = detect_all(scan_result.files)
        graph = build_graph(scan_result)
        centrality = graph.centrality_scores()

    token_map = {fi.relative_path: fi for fi in token_report.file_tokens}

    try:
        strat = Strategy(strategy)
    except ValueError:
        console.print(f"[red]Unknown strategy '{strategy}'. "
                      f"Use: budget | category | centrality | random[/red]")
        raise typer.Exit(1)

    result = do_sample(
        categorized=categorized,
        token_map=token_map,
        centrality_map=centrality,
        strategy=strat,
        budget=budget,
        per_category=per_category,
        top_n=top_n,
        exclude_tests=no_tests,
        seed=seed,
    )

    table = Table(title=f"Selected {len(result.files)} files "
                        f"({result.total_tokens:,} / {budget:,} tokens "
                        f"— {result.utilization:.1%})",
                  box=box.SIMPLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("File", style="white")
    table.add_column("Category", style="magenta")
    table.add_column("Language", style="cyan")
    table.add_column("Tokens", justify="right", style="yellow")
    table.add_column("Centrality", justify="right")
    for i, sf in enumerate(result.files, 1):
        table.add_row(str(i), sf.relative_path, sf.category.value,
                      sf.language, f"{sf.tokens:,}", f"{sf.centrality:.2f}")
    console.print(table)


# ---------------------------------------------------------------------------
# rco export
# ---------------------------------------------------------------------------

@app.command()
def export(
    repo: Path = typer.Argument(..., help="Path to the repository root."),
    output: Path = typer.Option(Path("context.md"), "--output", "-o",
                                 help="Output file path."),
    strategy: str = typer.Option("budget", "--strategy", "-s",
                                  help="budget | category | centrality | random"),
    budget: int = typer.Option(100_000, "--budget", "-b",
                                help="Max tokens in the output context."),
    per_category: int = typer.Option(3, "--per-category",
                                      help="(category strategy) Files per category."),
    top_n: int = typer.Option(30, "--top", help="(centrality strategy) Max files."),
    no_tests: bool = typer.Option(False, "--no-tests", help="Exclude test files."),
    compress: bool = typer.Option(False, "--compress", "-c",
                                   help="Strip comments to reduce token count."),
    model: str = typer.Option("claude", "--model", "-m", help="Tokenizer model family."),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed (random strategy)."),
) -> None:
    """
    [bold]Export[/bold] a sampled context file ready to paste into an LLM.
    """
    from rco.scanner.file_scanner import scan
    from rco.analyzer.token_counter import analyze as count
    from rco.analyzer.category_detector import detect_all
    from rco.analyzer.dependency_graph import build as build_graph
    from rco.sampler.sampler import sample as do_sample, Strategy
    from rco.exporter.flat_file import export as do_export

    console.print(Panel(
        f"[bold cyan]Exporting context[/bold cyan]  "
        f"repo=[white]{repo}[/white]  "
        f"output=[white]{output}[/white]\n"
        f"strategy=[yellow]{strategy}[/yellow]  "
        f"budget=[yellow]{budget:,}[/yellow] tokens  "
        f"compress=[yellow]{compress}[/yellow]",
        box=box.ROUNDED,
    ))

    with console.status("Scanning & analyzing…"):
        scan_result = scan(repo)
        token_report = count(scan_result, model=model)
        categorized = detect_all(scan_result.files)
        graph = build_graph(scan_result)
        centrality = graph.centrality_scores()

    token_map = {fi.relative_path: fi for fi in token_report.file_tokens}

    try:
        strat = Strategy(strategy)
    except ValueError:
        console.print(f"[red]Unknown strategy '{strategy}'.[/red]")
        raise typer.Exit(1)

    with console.status("Sampling files…"):
        result = do_sample(
            categorized=categorized,
            token_map=token_map,
            centrality_map=centrality,
            strategy=strat,
            budget=budget,
            per_category=per_category,
            top_n=top_n,
            exclude_tests=no_tests,
            seed=seed,
        )

    with console.status("Writing context file…"):
        written = do_export(result, output, repo_name=repo.name, compress=compress)

    console.print(Panel(
        f"[bold green]Done![/bold green]  Written to [white]{written}[/white]\n"
        f"Files: [yellow]{len(result.files)}[/yellow]  |  "
        f"Tokens: [yellow]{result.total_tokens:,}[/yellow] / {budget:,}  |  "
        f"Budget used: [yellow]{result.utilization:.1%}[/yellow]",
        box=box.ROUNDED,
    ))


if __name__ == "__main__":
    app()
