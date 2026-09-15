"""``write_scope`` matcher proof (ROLE-05, D-12, D-14) and
``validate_write_scope_patterns`` config-time validation coverage (A-05-13).

Pure functions only -- no git, no filesystem, no database (unit tier).

``05-RESEARCH.md``'s "Warning signs" note is the design brief here and is
honoured literally: a suite that only exercises single-level and
exactly-two-level paths catches **neither** failure mode of the wrong
(``pathlib``-based) matcher. The deep-nesting case below is at least three
segments below the pattern root, and the decoy case places the pattern's
root directory as a **non-leading** segment of a longer path -- the
canonical ``tests/fixtures/src/evil.py`` against ``src/**``. These two cases
exist specifically to fail against a right-anchored, path-component-count
matcher (the ``pathlib.PurePath.match()`` API this project deliberately does
not use); do not prune them as redundant with the single-level case.
"""

from __future__ import annotations

import pytest

from dark_factory.git.scope import is_out_of_scope, validate_write_scope_patterns

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# is_out_of_scope -- the matcher
# --------------------------------------------------------------------------- #


def test_single_level_match_is_in_scope() -> None:
    assert is_out_of_scope("src/app.py", ["src/**"]) is False


def test_deep_nesting_three_or_more_segments_below_the_pattern_root_is_in_scope() -> (
    None
):
    """The false-negative case a right-anchored matcher gets wrong: a path
    several segments below the pattern root must still match."""
    assert is_out_of_scope("src/sub/deep/nested/app.py", ["src/**"]) is False


def test_decoy_directory_with_the_pattern_root_as_a_non_leading_segment_is_out_of_scope() -> (
    None
):
    """The false-positive case a right-anchored (trailing-component-count)
    matcher gets wrong: the pattern's root directory name appearing as a
    later path segment must NOT match."""
    assert is_out_of_scope("tests/fixtures/src/evil.py", ["src/**"]) is True


def test_prefix_collision_is_out_of_scope() -> None:
    """``other/src/app.py`` is not ``src/**`` -- a naive substring or
    prefix-ish match would wrongly let this through."""
    assert is_out_of_scope("other/src/app.py", ["src/**"]) is True


def test_multi_pattern_disjunction_matches_any_one_pattern() -> None:
    write_scope = ["src/**", "docs/*.md"]
    assert is_out_of_scope("src/app.py", write_scope) is False
    assert is_out_of_scope("docs/readme.md", write_scope) is False
    assert is_out_of_scope("tests/test_app.py", write_scope) is True


def test_extension_scoped_pattern() -> None:
    write_scope = ["tests/**/*.py"]
    assert is_out_of_scope("tests/sub/test_app.py", write_scope) is False
    assert is_out_of_scope("tests/sub/fixture.json", write_scope) is True


def test_matching_is_case_sensitive_regardless_of_host_platform() -> None:
    assert is_out_of_scope("SRC/app.py", ["src/**"]) is True


def test_empty_write_scope_is_zero_tolerance_for_every_path() -> None:
    """D-14: an empty list means every path is a violation -- the opposite
    of 'unrestricted'. A test asserting the inverse would be asserting
    exactly the polarity D-14 forbids."""
    assert is_out_of_scope("anything.py", []) is True
    assert is_out_of_scope("src/app.py", []) is True
    assert is_out_of_scope("", []) is True


# --------------------------------------------------------------------------- #
# validate_write_scope_patterns -- config-time fail-loud validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pattern", ["src/**", "tests/**/*.py", "docs/*.md"], ids=lambda p: p
)
def test_well_formed_patterns_are_accepted(pattern: str) -> None:
    validate_write_scope_patterns([pattern], source="test-source")


def test_empty_string_pattern_is_rejected_naming_the_source() -> None:
    with pytest.raises(ValueError, match="test-source") as excinfo:
        validate_write_scope_patterns([""], source="test-source")
    assert "empty" in str(excinfo.value)


def test_whitespace_only_pattern_is_rejected() -> None:
    with pytest.raises(ValueError, match="test-source"):
        validate_write_scope_patterns(["   "], source="test-source")


def test_absolute_pattern_is_rejected_naming_the_pattern() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_write_scope_patterns(["/etc/passwd"], source="test-source")
    assert "/etc/passwd" in str(excinfo.value)
    assert "test-source" in str(excinfo.value)


def test_dot_slash_prefixed_pattern_is_rejected_naming_the_pattern() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_write_scope_patterns(["./src/**"], source="test-source")
    assert "./src/**" in str(excinfo.value)
    assert "test-source" in str(excinfo.value)


def test_parent_directory_escape_pattern_is_rejected_naming_the_pattern() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_write_scope_patterns(["../outside/**"], source="test-source")
    assert "../outside/**" in str(excinfo.value)
    assert "test-source" in str(excinfo.value)
