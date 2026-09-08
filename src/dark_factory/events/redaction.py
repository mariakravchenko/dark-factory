"""The one redaction path (Plan 01-03, Task 3 — D-14 through D-18).

``redact()`` is the *only* redaction implementation in the codebase: there is no
second scrubbing helper and no per-call-site ``.replace()``. It is wired in two
places — as a ``structlog`` processor (``dark_factory.logging``) and, from
Plan 04, inside the single lifecycle mutation path before every JSONB write.

Two modes (D-18):

* ``patterns=True`` (default) — exact-value substitution *and* the compiled
  D-15 pattern table. Used for every ``run_events.payload``, every
  ``role_executions.result`` / ``error`` and every log line.
* ``patterns=False`` (``scrub_known_values``) — exact-value substitution only.
  Used for the persisted task text (``runs.normalized_task`` / ``source_ref``)
  so a task that legitimately discusses connection-string syntax keeps its
  wording while a real leaked credential value is still removed everywhere.

Redaction is one-way: a value that reaches Neon or a log file unredacted cannot
be recalled, and an over-redacted value cannot be recovered either.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

# --- Sensitivity vocabulary (D-15 list) --------------------------------------

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "secret_key",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "database_url",
        "github_token",
        "authorization",
        "bearer",
    }
)

_KV_KEYS = "|".join(sorted(_SENSITIVE_KEYS))


def _kv_replacement(match: re.Match[str]) -> str:
    """``<key><sep><quote?>[redacted:<key-lowercased>]<quote?>`` for a sensitive
    ``key=value``.

    Group 3 is the optional opening quote that the pattern also requires as the
    closing delimiter (``\\3``); re-emit it on both sides so ``token="abc"``
    becomes ``token="[redacted:token]"`` and not the unbalanced
    ``token=[redacted:token]`` that could invalidate a surrounding JSON string
    (IN-06)."""
    quote = match.group(3)
    return (
        f"{match.group(1)}{match.group(2)}{quote}"
        f"[redacted:{match.group(1).lower()}]{quote}"
    )


# A 40-hex (classic PAT) or 64-hex token is redacted UNLESS the text right before
# it names it as a git object -- ``commit`` / ``sha`` / ``revision`` followed only
# by separators. Proximity to the literal "github" is deliberately NOT the gate:
# a bare 40-hex PAT in prose ("auth failed with <40hex>", "key: <40hex>") must be
# caught regardless (WR-06 / the D-15 pattern table is the only scrub for
# third-party credentials echoed into a WorkerResult).
_GIT_OBJECT_CONTEXT = re.compile(r"(?i)\b(?:commit|sha|revision)\b[\s:=#/-]*\Z")
_HEX_TOKEN = re.compile(r"\b[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\b")


def _hex_token_replacement(match: re.Match[str]) -> str:
    """Redact a standalone 40/64-hex token unless it is introduced as a git
    object hash (``commit <sha>`` etc.), which must survive (D-18)."""
    if _GIT_OBJECT_CONTEXT.search(match.string[: match.start()]):
        return match.group(0)
    return "[redacted:github_token]"


# --- Compiled pattern table (D-15). Compiled once at import. -----------------
#
# Order matters: the dedicated `Authorization: Bearer` rule and the token-shape
# rules run before the generic `key=value` rule so a bearer value cannot leak
# through the narrower `[^\s]+` capture of the generic rule.

_PATTERNS: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    # 1. Postgres / DB connection URI carrying embedded credentials. The
    #    credential span is `[^\s@]+` (everything up to the `@`), so a password
    #    containing a raw `/`, `:` or other special character does not defeat the
    #    match and leak the whole URI (WR-06).
    (
        re.compile(r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s@]+@\S+"),
        "[redacted:database_url]",
    ),
    # 3a. GitHub fine-grained PAT.
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "[redacted:github_token]"),
    # 3b. GitHub classic / OAuth token shapes (ghp_/gho_/ghu_/ghs_/ghr_).
    (re.compile(r"\b(gh[porsu])_[A-Za-z0-9]{36,}\b"), "[redacted:github_token]"),
    # 3c. Bare 40/64-hex token — redacted unconditionally except in a git-object
    #     context (see _hex_token_replacement / _GIT_OBJECT_CONTEXT).
    (_HEX_TOKEN, _hex_token_replacement),
    # 4. `Authorization: Bearer <value>` header. The token class includes the
    #    standard-base64 alphabet (`+`, `/`, `=`) so a base64 bearer value is
    #    fully consumed rather than leaving a trailing fragment (WR-06).
    (
        re.compile(r"(?i)authorization\"?\s*[:=]\s*\"?bearer\s+[A-Za-z0-9._\-+/=]+"),
        "[redacted:authorization]",
    ),
    # 2. Sensitive `key=value` / `key: value` pair.
    (
        re.compile(
            rf"(?i)\b({_KV_KEYS})\b(\s*[:=]\s*)(\"?)([^\s\"',}}]+)\3",
        ),
        _kv_replacement,
    ),
]


def _scrub_known(value: str, known_secrets: Mapping[str, str]) -> str:
    """Replace every live known secret value with ``[redacted:<label>]``.

    Longest value first, so a shorter secret that is a substring of a longer one
    cannot leave a fragment behind. Values shorter than 8 characters are skipped
    so a short or empty configured secret cannot turn this into a string
    shredder.
    """
    for secret, label in sorted(
        known_secrets.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if len(secret) >= 8 and secret in value:
            value = value.replace(secret, f"[redacted:{label}]")
    return value


def _redact_str(value: str, known_secrets: Mapping[str, str], *, patterns: bool) -> str:
    value = _scrub_known(value, known_secrets)
    if patterns:
        for compiled, replacement in _PATTERNS:
            value = compiled.sub(replacement, value)
    return value


def redact(
    value: Any,
    *,
    known_secrets: Mapping[str, str],
    patterns: bool = True,
) -> Any:
    """Recursively redact ``value``.

    * ``Mapping`` — a key whose lowercased form is in the sensitivity set has
      its value replaced by ``[redacted:<key>]`` regardless of the value's
      shape; every other value is redacted recursively.
    * ``list`` / ``tuple`` — redacted elementwise, always returned as a list.
    * ``set`` / ``frozenset`` — redacted elementwise, returned as a list (JSONB
      is JSON-typed, so this is defence-in-depth for a set of secret strings
      that should never reach a payload in the first place; IN-07).
    * ``bytes`` / ``bytearray`` — decoded as UTF-8, redacted as a string, and
      re-encoded to ``bytes``; returned unchanged if it is not valid UTF-8.
    * ``str`` — known-value substitution first, then (when ``patterns``) the
      compiled D-15 table.
    * anything else (``int`` / ``float`` / ``bool`` / ``None`` / ...) — returned
      unchanged.

    Idempotent: the ``[redacted:...]`` tokens are not re-matched by any rule.
    """
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
                redacted[key] = f"[redacted:{key.lower()}]"
            else:
                redacted[key] = redact(
                    item, known_secrets=known_secrets, patterns=patterns
                )
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            redact(item, known_secrets=known_secrets, patterns=patterns)
            for item in value
        ]
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return value
        return _redact_str(text, known_secrets, patterns=patterns).encode("utf-8")
    if isinstance(value, str):
        return _redact_str(value, known_secrets, patterns=patterns)
    return value


def scrub_known_values(value: Any, *, known_secrets: Mapping[str, str]) -> Any:
    """Exact-value substitution only — the ``patterns=False`` alias (D-18).

    This is what the persisted-task-text path uses, per the Task 1 decision
    checkpoint (``known-values-only``).
    """
    return redact(value, known_secrets=known_secrets, patterns=False)
