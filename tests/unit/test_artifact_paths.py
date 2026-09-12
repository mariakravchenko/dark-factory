"""Unit proofs for the T-04-01/02/03 artifact-path-safety and size-cap
mitigations (this plan's ``<threat_model>``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dark_factory.artifacts import (
    ArtifactPathError,
    ArtifactTooLargeError,
    MissingArtifactContentError,
)
from dark_factory.artifacts.paths import (
    _MAX_ARTIFACT_BYTES,
    checksum,
    ensure_run_tree,
    resolve_under_run_root,
)
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.artifacts.validation import collect_role_artifacts
from dark_factory.domain.worker import ArtifactRef

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# T-04-01 -- path-traversal / escape rejection
# --------------------------------------------------------------------------- #


def test_t_04_01_parent_directory_escape_raises(tmp_path: Path) -> None:
    """T-04-01: a ``..`` parent-directory traversal is rejected."""
    root = tmp_path / "run"
    root.mkdir()
    with pytest.raises(ArtifactPathError) as excinfo:
        resolve_under_run_root(root, "../escape.txt")
    assert "../escape.txt" in str(excinfo.value)


def test_t_04_01_absolute_path_outside_root_raises(tmp_path: Path) -> None:
    """T-04-01: an absolute path outside the run root is rejected, never
    silently reinterpreted as a path relative to the root."""
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(ArtifactPathError) as excinfo:
        resolve_under_run_root(root, str(outside))
    assert str(outside) in str(excinfo.value)


def test_t_04_01_symlink_escaping_root_raises(tmp_path: Path) -> None:
    """T-04-01: a symlink whose resolved target lands outside the run root is
    rejected -- the check is on the resolved path, not the link's own location."""
    root = tmp_path / "run"
    root.mkdir()
    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("outside content", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(outside_target)

    with pytest.raises(ArtifactPathError) as excinfo:
        resolve_under_run_root(root, "link.txt")
    assert "link.txt" in str(excinfo.value)


def test_t_04_01_legitimate_nested_path_resolves(tmp_path: Path) -> None:
    """T-04-01: a genuinely nested path under the root resolves normally."""
    root = tmp_path / "run"
    (root / "artifacts" / "BA").mkdir(parents=True)
    resolved = resolve_under_run_root(root, "artifacts/BA/file.json")
    assert resolved == (root / "artifacts" / "BA" / "file.json").resolve()


# --------------------------------------------------------------------------- #
# T-04-02 -- the size cap, checked before any parse
# --------------------------------------------------------------------------- #


def test_t_04_02_file_at_exactly_the_cap_succeeds(tmp_path: Path) -> None:
    """T-04-02: the boundary is inclusive -- exactly the cap passes."""
    root = tmp_path / "run"
    root.mkdir()
    (root / "at_cap.txt").write_bytes(b"a" * _MAX_ARTIFACT_BYTES)
    text = read_artifact_text(root, "at_cap.txt")
    assert len(text) == _MAX_ARTIFACT_BYTES


def test_t_04_02_one_byte_over_the_cap_raises(tmp_path: Path) -> None:
    """T-04-02: one byte over the cap raises, never silently truncates."""
    root = tmp_path / "run"
    root.mkdir()
    (root / "over_cap.txt").write_bytes(b"a" * (_MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ArtifactTooLargeError):
        read_artifact_text(root, "over_cap.txt")


def test_t_04_02_size_check_precedes_any_parse(tmp_path: Path) -> None:
    """T-04-02: an oversized file that is ALSO syntactically broken JSON still
    raises the size error, never a parse error -- ``read_artifact_text`` never
    parses content, so the size gate is structurally first."""
    root = tmp_path / "run"
    root.mkdir()
    malformed_and_oversized = b"{not valid json at all" + b"x" * _MAX_ARTIFACT_BYTES
    (root / "broken.json").write_bytes(malformed_and_oversized)

    with pytest.raises(ArtifactTooLargeError):
        read_artifact_text(root, "broken.json")


# --------------------------------------------------------------------------- #
# T-04-03 -- a missing file is a named error, never "artifact absent, continue"
# --------------------------------------------------------------------------- #


def test_t_04_03_missing_file_raises_naming_absolute_path(tmp_path: Path) -> None:
    """T-04-03: ``read_artifact_text`` raises naming the absolute path."""
    root = tmp_path / "run"
    root.mkdir()
    with pytest.raises(MissingArtifactContentError) as excinfo:
        read_artifact_text(root, "never_written.json")
    assert str((root / "never_written.json").resolve()) in str(excinfo.value)


def test_t_04_03_collect_role_artifacts_propagates_missing_file(
    tmp_path: Path,
) -> None:
    """T-04-03: a reported reference whose file was never written propagates
    ``MissingArtifactContentError`` out of ``collect_role_artifacts`` -- never
    treated as "no prior artifact"."""
    root = tmp_path / "run"
    root.mkdir()
    refs = [ArtifactRef(type="missing.json", path="missing.json", checksum=None)]

    with pytest.raises(MissingArtifactContentError):
        collect_role_artifacts(root, "BA", "irrelevant-id", ["missing.json"], refs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# checksum + ensure_run_tree idempotency
# --------------------------------------------------------------------------- #


def test_checksum_is_sha256_hex_digest() -> None:
    data = b"hello artifact"
    assert checksum(data) == hashlib.sha256(data).hexdigest()


def test_ensure_run_tree_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "run"
    ensure_run_tree(root)
    ensure_run_tree(root)  # must not raise
    for child in ("input", "artifacts", "verification", "logs"):
        assert (root / child).is_dir()
