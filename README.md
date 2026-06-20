# Repo Context Optimizer (rco)

> Analyze and sample code repositories to prepare high-quality context for LLMs.

Instead of dumping an entire codebase into a prompt, `rco` helps you select the **most representative and relevant files** within a token budget — respecting architectural roles (controllers, services, models…) and file importance (centrality in the import graph).

---

## Features

- **Token analysis** — count tokens per file, folder and total, broken down by language and category
- **Category detection** — automatically classifies files as `controller`, `service`, `repository`, `model`, `component`, `hook`, `util`, `config`, `test`… using path patterns and Java annotations
- **Dependency graph** — builds an import graph to rank files by centrality (how many other files import them)
- **Smart sampling** — four strategies to select files within a token budget:
  - `budget` — greedy knapsack balancing centrality and token efficiency (default)
  - `category` — N files per category for maximum diversity
  - `centrality` — most-imported files first
  - `random` — stratified random sample
- **Flat file export** — generates a single `.md` file with a summary table and all selected code, ready to paste into Claude, ChatGPT, or any LLM
- **Comment stripping** — optional compression to reduce token count while preserving intent
- Respects `.gitignore` automatically

---

## Supported languages

| Language | Token counting | Category detection | Dependency graph |
|----------|---------------|--------------------|-----------------|
| Java | ✅ | ✅ (annotations + naming) | ✅ (import statements) |
| TypeScript / TSX | ✅ | ✅ (naming conventions) | ✅ (import/require) |
| JavaScript / JSX | ✅ | ✅ (naming conventions) | ✅ (import/require) |
| Python, Go, Rust, … | ✅ | Partial (path-based) | ❌ planned |

---

## Installation

### Requirements

- Python 3.10+
- pip

### From source

```bash
git clone https://github.com/YOUR_USERNAME/repo-context-optimizer.git
cd repo-context-optimizer
pip install -e ".[dev]"
```

### Verify installation

```bash
rco --version
```

---

## Usage

### Analyze a repository

```bash
rco analyze ./my-project
rco analyze ./my-project --model gpt-4o --top 30
```

Output: token count by language, file category breakdown, top heaviest files.

### Preview sampling

```bash
# Default: budget strategy, 100k tokens
rco sample ./my-project

# Category strategy: 2 files per category, 80k token budget
rco sample ./my-project --strategy category --per-category 2 --budget 80000

# Most-imported files first
rco sample ./my-project --strategy centrality --top 15

# Exclude test files
rco sample ./my-project --no-tests
```

### Export context file

```bash
# Default export (budget strategy, 100k tokens)
rco export ./my-project --output context.md

# Category strategy with comment stripping
rco export ./my-project --strategy category --per-category 3 --compress --output context.md

# Full pipeline example
rco export ./my-project \
  --strategy budget \
  --budget 80000 \
  --no-tests \
  --compress \
  --model claude \
  --output ./context/my-project-context.md
```

---

## Output format

The exported `.md` file looks like this:

```markdown
# Repo Context — my-project
> Generated: 2026-06-17 12:00  |  Files: 18  |  Tokens: 47,832 / 100,000  |  Budget used: 47.8%  |  Strategy: budget

## Selected files

| # | File | Category | Language | Tokens | Centrality |
|---|------|----------|----------|--------|------------|
| 1 | src/main/java/com/app/UserController.java | controller | java | 1,243 | 0.87 |
| 2 | src/services/auth.service.ts | service | typescript | 891 | 0.72 |
...

---

## [1/18] src/main/java/com/app/UserController.java
> **Category:** controller  |  **Tokens:** 1,243  |  **Centrality:** 0.87

```java
// ...code...
```
```

---

## Token model support

| Flag | Encoding | Best for |
|------|----------|---------|
| `claude` | cl100k_base (approx.) | Claude models |
| `gpt-4o` | o200k_base | GPT-4o |
| `gpt-4` | cl100k_base | GPT-4 / GPT-3.5 |
| `gemini` | cl100k_base (approx.) | Gemini models |

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=rco --cov-report=term-missing

# Lint
ruff check rco/
```

---

## Roadmap

- [ ] GitHub / GitLab remote repo support
- [ ] Python dependency graph (`import` analysis)
- [ ] Tree-sitter integration for deeper structural analysis (extract only function signatures)
- [ ] Interactive TUI mode
- [ ] Config file (`.rcorc`) for persistent preferences
- [ ] XML output format (better for Claude's context window usage)
- [ ] VS Code extension

---

## License

MIT
