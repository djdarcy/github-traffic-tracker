"""Smoke tests for preserve_lib — hash, compare, metadata, verify, manifest.

These validate that the ported preserve_lib works correctly in the ghtraf
context and that its shared types are identity-linked to core_lib.
"""

import os
import hashlib
import tempfile
from pathlib import Path

import pytest

from ghtraf.lib.core_lib.types import FileCategory, ConflictResolution
from ghtraf.lib.preserve_lib import (
    # Core types (should be same objects as core_lib)
    FileCategory as PL_FileCategory,
    ConflictResolution as PL_ConflictResolution,
    # Manifest / hashing
    PreserveManifest,
    calculate_file_hash,
    verify_file_hash,
    # Destination scanning
    FileComparison,
    DestinationScanResult,
    compare_files,
    scan_destination,
    # Metadata
    collect_file_metadata,
    # Verification
    VerificationStatus,
    FileVerificationResult,
    VerificationResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_file(tmp_path):
    """Create a temporary file with known content."""
    f = tmp_path / "sample.txt"
    f.write_text("hello preserve_lib\n")
    return f


@pytest.fixture
def tmp_file_pair(tmp_path):
    """Create source and dest dirs with identical and conflicting files."""
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    dst.mkdir()

    # Identical file
    (src / "same.txt").write_text("identical content")
    (dst / "same.txt").write_text("identical content")

    # Conflicting file
    (src / "differ.txt").write_text("source version")
    (dst / "differ.txt").write_text("dest version")

    # Source-only file
    (src / "new.txt").write_text("only in source")

    return src, dst


# ── Enum Identity Tests ──────────────────────────────────────────────

class TestEnumIdentity:
    """preserve_lib types must be the SAME objects as core_lib types."""

    def test_file_category_is_same_object(self):
        assert PL_FileCategory is FileCategory

    def test_conflict_resolution_is_same_object(self):
        assert PL_ConflictResolution is ConflictResolution

    def test_file_category_members_accessible(self):
        assert PL_FileCategory.IDENTICAL.value == "identical"
        assert PL_FileCategory.CONFLICT.value == "conflict"
        assert PL_FileCategory.SOURCE_ONLY.value == "source_only"
        assert PL_FileCategory.DEST_ONLY.value == "dest_only"

    def test_conflict_resolution_members_accessible(self):
        assert PL_ConflictResolution.SKIP.value == "skip"
        assert PL_ConflictResolution.OVERWRITE.value == "overwrite"
        assert PL_ConflictResolution.RENAME.value == "rename"


# ── Hash Tests ────────────────────────────────────────────────────────

class TestCalculateFileHash:
    """calculate_file_hash() produces correct digests."""

    def test_sha256_default(self, tmp_file):
        result = calculate_file_hash(tmp_file)
        assert "SHA256" in result
        # Verify against stdlib
        expected = hashlib.sha256(tmp_file.read_bytes()).hexdigest()
        assert result["SHA256"] == expected

    def test_multiple_algorithms(self, tmp_file):
        result = calculate_file_hash(tmp_file, ["SHA256", "MD5"])
        assert "SHA256" in result
        assert "MD5" in result
        expected_md5 = hashlib.md5(tmp_file.read_bytes()).hexdigest()
        assert result["MD5"] == expected_md5

    def test_nonexistent_file_returns_empty(self, tmp_path):
        result = calculate_file_hash(tmp_path / "nonexistent.txt")
        assert result == {}

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        result = calculate_file_hash(f)
        expected = hashlib.sha256(b"").hexdigest()
        assert result["SHA256"] == expected


class TestVerifyFileHash:
    """verify_file_hash() detects integrity correctly."""

    def test_correct_hash_verifies(self, tmp_file):
        expected_hash = hashlib.sha256(tmp_file.read_bytes()).hexdigest()
        ok, details = verify_file_hash(tmp_file, {"SHA256": expected_hash})
        assert ok is True
        assert details["SHA256"][0] is True  # match bool

    def test_wrong_hash_fails(self, tmp_file):
        ok, details = verify_file_hash(tmp_file, {"SHA256": "0" * 64})
        assert ok is False
        assert details["SHA256"][0] is False

    def test_empty_expected_returns_false(self, tmp_file):
        ok, details = verify_file_hash(tmp_file, {})
        assert ok is False


# ── Metadata Tests ────────────────────────────────────────────────────

class TestCollectFileMetadata:
    """collect_file_metadata() returns valid metadata dicts."""

    def test_has_required_keys(self, tmp_file):
        meta = collect_file_metadata(tmp_file)
        assert "mode" in meta
        assert "timestamps" in meta
        assert "size" in meta

    def test_size_matches(self, tmp_file):
        meta = collect_file_metadata(tmp_file)
        assert meta["size"] == tmp_file.stat().st_size

    def test_timestamps_present(self, tmp_file):
        meta = collect_file_metadata(tmp_file)
        ts = meta["timestamps"]
        assert "modified" in ts
        assert "accessed" in ts
        assert "created" in ts
        assert "modified_iso" in ts


# ── Destination Compare Tests ─────────────────────────────────────────

class TestCompareFiles:
    """compare_files() detects identical/conflict/source-only categories."""

    def test_identical_files(self, tmp_file_pair):
        src, dst = tmp_file_pair
        result = compare_files(src / "same.txt", dst / "same.txt")
        assert result.category == FileCategory.IDENTICAL
        assert result.source_hash is not None
        assert result.dest_hash is not None
        assert result.source_hash == result.dest_hash

    def test_conflicting_files(self, tmp_file_pair):
        src, dst = tmp_file_pair
        result = compare_files(src / "differ.txt", dst / "differ.txt")
        assert result.category == FileCategory.CONFLICT

    def test_source_only(self, tmp_file_pair):
        src, dst = tmp_file_pair
        result = compare_files(src / "new.txt", dst / "nonexistent.txt")
        assert result.category == FileCategory.SOURCE_ONLY

    def test_returns_file_comparison_type(self, tmp_file_pair):
        src, dst = tmp_file_pair
        result = compare_files(src / "same.txt", dst / "same.txt")
        assert isinstance(result, FileComparison)


class TestScanDestination:
    """scan_destination() categorizes all files correctly."""

    def test_scan_categorizes_all_files(self, tmp_file_pair):
        src, dst = tmp_file_pair
        source_files = list(src.iterdir())
        result = scan_destination(
            source_files, dst,
            path_style="flat",
            quick_check=False,
        )
        assert isinstance(result, DestinationScanResult)
        assert result.total_source_files == 3

        # Check counts — 1 identical, 1 conflict, 1 source-only
        assert result.identical_count == 1
        assert result.conflict_count == 1
        assert result.source_only_count == 1

    def test_scan_empty_destination(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "file.txt").write_text("content")

        result = scan_destination(
            [src / "file.txt"], dst,
            path_style="flat",
        )
        assert result.source_only_count == 1
        assert result.conflict_count == 0
        assert result.identical_count == 0


# ── Manifest Tests ────────────────────────────────────────────────────

class TestPreserveManifest:
    """PreserveManifest creates and tracks file records."""

    def test_new_manifest_has_structure(self):
        m = PreserveManifest()
        assert m.manifest["manifest_version"] == 3
        assert "manifest_id" in m.manifest
        assert m.manifest["manifest_id"].startswith("pm-")
        assert isinstance(m.manifest["files"], dict)
        assert isinstance(m.manifest["operations"], list)

    def test_manifest_id_is_unique(self):
        m1 = PreserveManifest()
        m2 = PreserveManifest()
        assert m1.manifest["manifest_id"] != m2.manifest["manifest_id"]

    def test_platform_info_populated(self):
        m = PreserveManifest()
        p = m.manifest["platform"]
        assert "system" in p
        assert "python_version" in p


# ── Verification Types Tests ──────────────────────────────────────────

class TestVerificationTypes:
    """Verification status and result types work correctly."""

    def test_verification_status_values(self):
        assert VerificationStatus.VERIFIED.value == "verified"
        assert VerificationStatus.FAILED.value == "failed"
        assert VerificationStatus.NOT_FOUND.value == "not_found"

    def test_file_verification_result_properties(self):
        r = FileVerificationResult(
            file_path=Path("test.txt"),
            status=VerificationStatus.VERIFIED,
        )
        assert r.is_verified is True
        assert r.is_failed is False

    def test_verification_result_aggregation(self):
        vr = VerificationResult()
        vr.add_result(FileVerificationResult(
            file_path=Path("a.txt"), status=VerificationStatus.VERIFIED))
        vr.add_result(FileVerificationResult(
            file_path=Path("b.txt"), status=VerificationStatus.VERIFIED))
        vr.add_result(FileVerificationResult(
            file_path=Path("c.txt"), status=VerificationStatus.FAILED))

        assert vr.total_files == 3
        assert vr.verified_count == 2
        assert vr.is_successful is False  # has 1 failure
        assert vr.success_rate == pytest.approx(2 / 3)

    def test_all_verified_is_successful(self):
        vr = VerificationResult()
        vr.add_result(FileVerificationResult(
            file_path=Path("x.txt"), status=VerificationStatus.VERIFIED))
        assert vr.is_successful is True
