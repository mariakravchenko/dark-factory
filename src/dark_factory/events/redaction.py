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
# by separators, or the phrase ``head at`` (the D-08 detached-HEAD error message's
# "has a detached HEAD at <sha>" wording). Proximity to the literal "github" is
# deliberately NOT the gate: a bare 40-hex PAT in prose ("auth failed with
# <40hex>", "key: <40hex>") must be caught regardless (WR-06 / the D-15 pattern
# table is the only scrub for third-party credentials echoed into a
# WorkerResult). The ``head at`` arm is deliberately narrow -- it requires
# ``head`` immediately followed by the separator word ``at``, not a bare ``at``
# on its own, so an unrelated "... failed at <40hex>" is still redacted.
_GIT_OBJECT_CONTEXT = re.compile(
    r"(?i)(?:\b(?:commit|sha|revision)\b[\s:=#/-]*|\bhead\b\s+at\s+)\Z"
)
_HEX_TOKEN = re.compile(r"\b[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\b")

# Dict keys whose value is a git object identifier (a commit SHA), never a
# secret -- when `redact()` recurses into a Mapping under one of these keys,
# the bare hex-token pattern is skipped for that value (D-15/WR-06 mislabels a
# key-value pair like `{"commit": "<40hex>"}` as a token because the recursive
# per-value redaction has no visibility into its own key name). This exemption
# applies ONLY to `_HEX_TOKEN` -- every other pattern (github_pat_, gh[porsu]_,
# postgres URLs, bearer tokens) still redacts unconditionally under these keys,
# because those shapes are never legitimately a commit SHA.
_GIT_OBJECT_KEYS: frozenset[str] = frozenset(
    {
        "commit",
        "sha",
        "revision",
        "commit_sha",
        "wip_commit_sha",
    }
)

# Dict keys whose value is a CONTENT DIGEST, never a secret. A SHA-256 artifact
# checksum (``ArtifactRef.checksum``) is exactly 64 hex characters, so it is
# indistinguishable BY SHAPE from a bare 64-hex credential -- which made
# `_HEX_TOKEN` destroy every checksum serialized into `role_executions.result`
# (on every artifact-producing role attempt) and `role_executions.error` (on a
# FAILED role): both columns store the same `WorkerResult.model_dump()` blob.
# `artifact_references.checksum` was never affected -- it is assigned without
# redaction and remains the system of record.
#
# This follows the `_GIT_OBJECT_KEYS` seam above but is deliberately NARROWER in
# three ways, because a checksum in an audit blob is a legibility nicety and is
# not worth one millimetre of the redactor's default-deny posture:
#
#   1. SHAPE-GATED, not key-only. The value must match `_SHA256_DIGEST` exactly
#      -- 64 *lowercase* hex characters end to end, which is precisely what
#      `hashlib.sha256(...).hexdigest()` emits (see artifacts/paths.py). So a
#      40-hex classic PAT, an upper/mixed-case 64-hex run, and any value with
#      surrounding prose are ALL still redacted under a `checksum` key.
#   2. `_HEX_TOKEN` ONLY. Every other pattern row (github_pat_, gh[porsu]_,
#      postgres URIs, bearer headers, the sensitive key=value rule) still runs
#      unconditionally -- none of those shapes is ever legitimately a digest.
#   3. KNOWN VALUES ARE STILL SCRUBBED. `_scrub_known` runs before the pattern
#      table inside `_redact_str` and is never exempted, so a configured live
#      secret that happens to be 64 lowercase hex characters is still removed
#      from a `checksum` field. This is what stops the fix from turning an
#      over-redaction (safe) into a credential leak (not safe).
#
# Defensible because `checksum` is not a worker-controlled free-text field:
# every production `ArtifactRef` carries a digest Dark Factory computed itself
# from bytes it read (workers/cli_runtime.py, workers/fake.py), so no untrusted
# value reaches this key. Do NOT add a key here whose value an agent can author,
# and do NOT mirror this as a TEXTUAL `_GIT_OBJECT_CONTEXT` arm -- a prose rule
# matching "checksum: <64hex>" would be trivially forgeable by an untrusted
# worker, which is exactly the surface WR-06 / the D-15 table exists to cover.
_CHECKSUM_KEYS: frozenset[str] = frozenset({"checksum"})
_SHA256_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


def _is_sha256_digest(value: Any) -> bool:
    """True only for a string that is exactly a lowercase SHA-256 hex digest."""
    return isinstance(value, str) and _SHA256_DIGEST.match(value) is not None


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


def _redact_str(
    value: str,
    known_secrets: Mapping[str, str],
    *,
    patterns: bool,
    exempt_hex_token: bool = False,
) -> str:
    value = _scrub_known(value, known_secrets)
    if patterns:
        for compiled, replacement in _PATTERNS:
            if exempt_hex_token and compiled is _HEX_TOKEN:
                continue
            value = compiled.sub(replacement, value)
    return value


def redact(
    value: Any,
    *,
    known_secrets: Mapping[str, str],
    patterns: bool = True,
    exempt_hex_token: bool = False,
) -> Any:
    """Recursively redact ``value``.

    * ``Mapping`` — a key whose lowercased form is in the sensitivity set has
      its value replaced by ``[redacted:<key>]`` regardless of the value's
      shape; a key whose lowercased form is in ``_GIT_OBJECT_KEYS`` (``commit``,
      ``sha``, ``revision``, ...) is redacted recursively with the bare
      hex-token pattern exempted for that value only -- every other pattern
      (github_pat_, gh[porsu]_, postgres URLs, bearer tokens) still applies
      unconditionally, because those shapes are never legitimately a commit
      SHA. A key in ``_CHECKSUM_KEYS`` (``checksum``) gets the same hex-token
      exemption but only when its value is exactly a lowercase SHA-256 digest
      (``_SHA256_DIGEST``) -- a 40-hex run, an upper-case 64-hex run or any
      value with surrounding prose is still redacted there. Every other value
      is redacted recursively with no exemption.

      No exemption ever skips ``_scrub_known``: a configured live secret value
      is removed under every key, whatever its shape.
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
                item_exempt = isinstance(key, str) and (
                    key.lower() in _GIT_OBJECT_KEYS
                    # Shape-gated: a `checksum` key earns the exemption only for
                    # a value that IS a lowercase SHA-256 digest, so a secret
                    # shape parked under this key is still redacted.
                    or (key.lower() in _CHECKSUM_KEYS and _is_sha256_digest(item))
                )
                redacted[key] = redact(
                    item,
                    known_secrets=known_secrets,
                    patterns=patterns,
                    exempt_hex_token=item_exempt,
                )
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            redact(
                item,
                known_secrets=known_secrets,
                patterns=patterns,
                exempt_hex_token=exempt_hex_token,
            )
            for item in value
        ]
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return value
        return _redact_str(
            text, known_secrets, patterns=patterns, exempt_hex_token=exempt_hex_token
        ).encode("utf-8")
    if isinstance(value, str):
        return _redact_str(
            value, known_secrets, patterns=patterns, exempt_hex_token=exempt_hex_token
        )
    return value


def scrub_known_values(value: Any, *, known_secrets: Mapping[str, str]) -> Any:
    """Exact-value substitution only — the ``patterns=False`` alias (D-18).

    This is what the persisted-task-text path uses, per the Task 1 decision
    checkpoint (``known-values-only``).
    """
    return redact(value, known_secrets=known_secrets, patterns=False)
