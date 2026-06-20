"""Token counter: estimates token usage per file and for the whole repo."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from rco.scanner.file_scanner import ScannedFile, ScanResult

# Map model families to their tiktoken encoding
_ENCODING_MAP = {
    "gpt-4o": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5": "cl100k_base",
    # Claude / Gemini don't have official tiktoken encodings;
    # cl100k_base is a good approximation (within ~5%)
    "claude": "cl100k_base",
    "gemini": "cl100k_base",
    "default": "cl100k_base",
}


@dataclass
class FileTokenInfo:
    scanned_file: ScannedFile
    tokens: int

    @property
    def relative_path(self) -> str:
        return self.scanned_file.relative_path

    @property
    def language(self) -> str:
        return self.scanned_file.language


@dataclass
class TokenReport:
    model: str
    file_tokens: list[FileTokenInfo]
    total_tokens: int

    def top_files(self, n: int = 20) -> list[FileTokenInfo]:
        return sorted(self.file_tokens, key=lambda f: f.tokens, reverse=True)[:n]

    def by_language(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for fi in self.file_tokens:
            result[fi.language] = result.get(fi.language, 0) + fi.tokens
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))


def _get_encoder(model: str):
    """Return a tiktoken encoder or None if the vocabulary cannot be downloaded."""
    encoding_name = _ENCODING_MAP.get(model, _ENCODING_MAP["default"])
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        # Offline / restricted network: fall back to char-count estimation.
        return None


def count_tokens(text: str, encoder) -> int:
    """Count tokens for a given string.

    Uses tiktoken when available; otherwise estimates via character count / 4,
    which is a widely-used approximation for English/code text.
    """
    if encoder is not None:
        return len(encoder.encode(text, disallowed_special=()))
    return max(1, len(text) // 4)


def analyze(scan_result: ScanResult, model: str = "claude") -> TokenReport:
    """
    Count tokens for every file in *scan_result*.

    Args:
        scan_result: Result from file_scanner.scan().
        model: Target model family for token counting. One of:
               'claude', 'gpt-4o', 'gpt-4', 'gpt-3.5', 'gemini', 'default'.
    """
    encoder = _get_encoder(model)
    file_tokens: list[FileTokenInfo] = []
    total = 0

    for sf in scan_result.files:
        text = sf.read_text()
        tokens = count_tokens(text, encoder)
        total += tokens
        file_tokens.append(FileTokenInfo(scanned_file=sf, tokens=tokens))

    return TokenReport(model=model, file_tokens=file_tokens, total_tokens=total)
