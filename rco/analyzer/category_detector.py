"""Category detector: classifies each file by its architectural role."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from rco.scanner.file_scanner import ScannedFile


class Category(str, Enum):
    CONTROLLER = "controller"
    SERVICE = "service"
    REPOSITORY = "repository"
    MODEL = "model"
    COMPONENT = "component"      # React / Vue / Angular components
    HOOK = "hook"                # React hooks
    UTIL = "util"
    CONFIG = "config"
    TEST = "test"
    MIDDLEWARE = "middleware"
    ROUTE = "route"
    SCHEMA = "schema"            # DB schemas, Zod, Joi, etc.
    MIGRATION = "migration"
    UNKNOWN = "unknown"


@dataclass
class CategorizedFile:
    scanned_file: ScannedFile
    category: Category
    confidence: float            # 0.0 – 1.0

    @property
    def relative_path(self) -> str:
        return self.scanned_file.relative_path

    @property
    def language(self) -> str:
        return self.scanned_file.language


# ---------------------------------------------------------------------------
# Rules: each rule is (pattern_against_path, optional_content_pattern, category, confidence)
# Rules are evaluated in order; first match wins.
# ---------------------------------------------------------------------------

_PATH_RULES: list[tuple[str, Category, float]] = [
    # Tests (check first — a test can match other rules too)
    (r"(test|spec|__tests__|__mocks__|e2e)[/\\]", Category.TEST, 0.95),
    (r"\.(test|spec)\.(java|kt|js|jsx|ts|tsx|py)$", Category.TEST, 0.98),
    (r"Test\.java$", Category.TEST, 0.98),

    # Migrations
    (r"(migration|migrations)[/\\]", Category.MIGRATION, 0.95),
    (r"V\d+__.*\.sql$", Category.MIGRATION, 0.99),

    # Config / infrastructure
    (r"(application|bootstrap)\.(properties|yml|yaml)$", Category.CONFIG, 0.95),
    (r"(webpack|vite|rollup|babel|jest|eslint|prettier|tsconfig|dockerfile"
     r"|docker-compose|\.env).*$", Category.CONFIG, 0.90),

    # Java conventions
    (r"Controller\.java$", Category.CONTROLLER, 0.97),
    (r"Service\.java$|ServiceImpl\.java$", Category.SERVICE, 0.97),
    (r"Repository\.java$|Dao\.java$|DaoImpl\.java$", Category.REPOSITORY, 0.97),
    (r"(Entity|Model|Dto|DTO|Request|Response|VO)\.java$", Category.MODEL, 0.90),
    (r"Middleware\.java$|Filter\.java$|Interceptor\.java$", Category.MIDDLEWARE, 0.90),

    # JS/TS naming conventions
    (r"\.controller\.(js|jsx|ts|tsx)$", Category.CONTROLLER, 0.97),
    (r"\.service\.(js|jsx|ts|tsx)$", Category.SERVICE, 0.97),
    (r"\.repository\.(js|jsx|ts|tsx)$|\.repo\.(js|jsx|ts|tsx)$", Category.REPOSITORY, 0.97),
    (r"\.(model|entity|dto|schema)\.(js|jsx|ts|tsx)$", Category.MODEL, 0.93),
    (r"\.component\.(js|jsx|ts|tsx)$", Category.COMPONENT, 0.97),
    (r"use[A-Z][A-Za-z]+\.(js|jsx|ts|tsx)$", Category.HOOK, 0.95),  # useMyHook.ts
    (r"(hooks|hook)[/\\]", Category.HOOK, 0.85),
    (r"\.(middleware)\.(js|jsx|ts|tsx)$", Category.MIDDLEWARE, 0.95),
    (r"\.(route|router)\.(js|jsx|ts|tsx)$|routes?[/\\]", Category.ROUTE, 0.90),
    (r"\.(util|utils|helper|helpers|lib)\.(js|jsx|ts|tsx)$", Category.UTIL, 0.90),
    (r"(utils|helpers|lib|shared)[/\\]", Category.UTIL, 0.75),

    # Generic components directory
    (r"(components|pages|views|screens)[/\\]", Category.COMPONENT, 0.75),
    (r"\.(jsx|tsx)$", Category.COMPONENT, 0.60),   # low confidence default for JSX/TSX
]

# Java annotation → category (applied to file content, first 60 lines)
_JAVA_ANNOTATION_RULES: list[tuple[str, Category, float]] = [
    (r"@(Rest)?Controller", Category.CONTROLLER, 0.99),
    (r"@(Rest)?ControllerAdvice", Category.CONTROLLER, 0.99),
    (r"@Service", Category.SERVICE, 0.99),
    (r"@Repository", Category.REPOSITORY, 0.99),
    (r"@(Entity|Document|Table)", Category.MODEL, 0.97),
    (r"@(Configuration|SpringBootApplication|EnableAutoConfiguration)", Category.CONFIG, 0.97),
]


def _head(text: str, lines: int = 60) -> str:
    return "\n".join(text.splitlines()[:lines])


def detect(sf: ScannedFile) -> CategorizedFile:
    path = sf.relative_path.replace("\\", "/").lower()

    # 1. Path-based rules
    for pattern, category, confidence in _PATH_RULES:
        if re.search(pattern, path, re.IGNORECASE):
            return CategorizedFile(sf, category, confidence)

    # 2. Java annotation scan (only for Java files not caught by path)
    if sf.language == "java":
        text = _head(sf.read_text())
        for pattern, category, confidence in _JAVA_ANNOTATION_RULES:
            if re.search(pattern, text):
                return CategorizedFile(sf, category, confidence)

    return CategorizedFile(sf, Category.UNKNOWN, 0.0)


def detect_all(files: list[ScannedFile]) -> list[CategorizedFile]:
    return [detect(f) for f in files]
