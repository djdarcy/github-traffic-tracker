"""
plan_lib.file_ops — File comparison and destination scanning.

Bridges plan_lib with dazzle_filekit for file-level operations.
Provides FileComparison, DestinationScanResult, compare_files(),
and scan_destination() — the building blocks for creating file-based
plans in consumer applications.

dazzle_filekit dependency:
    Uses calculate_file_hash() and collect_file_metadata() from
    dazzle_filekit. If dazzle_filekit is not installed, file_ops
    gracefully degrades to basic os.path comparisons (size + mtime).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ghtraf.lib.core_lib import FileCategory

# Optional dazzle_filekit integration
try:
    from dazzle_filekit import calculate_file_hash, collect_file_metadata
    _HAS_FILEKIT = True
except ImportError:
    _HAS_FILEKIT = False


@dataclass
class FileComparison:
    """Result of comparing a source file to a destination file.

    Captures the relationship between two file paths including hash
    comparison, size, and modification times.
    """
    rel_path: str
    category: FileCategory
    source_path: Optional[str] = None
    dest_path: Optional[str] = None
    source_hash: Optional[str] = None
    dest_hash: Optional[str] = None
    source_size: Optional[int] = None
    dest_size: Optional[int] = None
    source_mtime: Optional[float] = None
    dest_mtime: Optional[float] = None

    @property
    def is_conflict(self) -> bool:
        return self.category == FileCategory.CONFLICT

    @property
    def is_identical(self) -> bool:
        return self.category == FileCategory.IDENTICAL

    def to_details(self) -> dict:
        """Convert to a dict suitable for Action.details."""
        d: dict = {"rel_path": self.rel_path, "category": self.category.value}
        if self.source_hash:
            d["source_hash"] = self.source_hash
        if self.dest_hash:
            d["dest_hash"] = self.dest_hash
        if self.source_size is not None:
            d["source_size"] = self.source_size
        if self.dest_size is not None:
            d["dest_size"] = self.dest_size
        return d


@dataclass
class DestinationScanResult:
    """Result of scanning a destination directory against source files.

    Groups FileComparisons by category for easy plan generation.
    """
    comparisons: list[FileComparison] = field(default_factory=list)

    @property
    def identical(self) -> list[FileComparison]:
        return [c for c in self.comparisons if c.category == FileCategory.IDENTICAL]

    @property
    def conflicts(self) -> list[FileComparison]:
        return [c for c in self.comparisons if c.category == FileCategory.CONFLICT]

    @property
    def source_only(self) -> list[FileComparison]:
        return [c for c in self.comparisons if c.category == FileCategory.SOURCE_ONLY]

    @property
    def dest_only(self) -> list[FileComparison]:
        return [c for c in self.comparisons if c.category == FileCategory.DEST_ONLY]

    @property
    def has_conflicts(self) -> bool:
        return any(c.is_conflict for c in self.comparisons)

    def summary(self) -> dict[str, int]:
        """Return a category → count mapping."""
        return {
            "identical": len(self.identical),
            "conflict": len(self.conflicts),
            "source_only": len(self.source_only),
            "dest_only": len(self.dest_only),
            "total": len(self.comparisons),
        }


def _hash_file(path: str, algorithm: str = "sha256") -> str:
    """Hash a file, using dazzle_filekit if available."""
    if _HAS_FILEKIT:
        result = calculate_file_hash(path, algorithms=[algorithm])
        return result[algorithm]
    # Fallback: stdlib hashlib
    import hashlib
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compare_files(
    source_path: str | Path,
    dest_path: str | Path,
    rel_path: str,
    *,
    algorithm: str = "sha256",
    quick: bool = False,
) -> FileComparison:
    """Compare a source file to a destination file.

    Args:
        source_path: Absolute path to the source file.
        dest_path: Absolute path to the destination file.
        rel_path: Relative path (used as the comparison key).
        algorithm: Hash algorithm for content comparison.
        quick: If True, compare size + mtime only (skip hash).

    Returns:
        FileComparison with category and metadata.
    """
    src = str(source_path)
    dst = str(dest_path)
    src_exists = os.path.isfile(src)
    dst_exists = os.path.isfile(dst)

    if src_exists and not dst_exists:
        stat = os.stat(src)
        return FileComparison(
            rel_path=rel_path,
            category=FileCategory.SOURCE_ONLY,
            source_path=src,
            source_size=stat.st_size,
            source_mtime=stat.st_mtime,
        )

    if not src_exists and dst_exists:
        stat = os.stat(dst)
        return FileComparison(
            rel_path=rel_path,
            category=FileCategory.DEST_ONLY,
            dest_path=dst,
            dest_size=stat.st_size,
            dest_mtime=stat.st_mtime,
        )

    if not src_exists and not dst_exists:
        # Both missing — shouldn't happen normally, but handle gracefully
        return FileComparison(
            rel_path=rel_path,
            category=FileCategory.SOURCE_ONLY,
        )

    # Both exist — compare
    src_stat = os.stat(src)
    dst_stat = os.stat(dst)

    # Quick mode: size + mtime only
    if quick:
        if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime == dst_stat.st_mtime:
            category = FileCategory.IDENTICAL
        else:
            category = FileCategory.CONFLICT
        return FileComparison(
            rel_path=rel_path,
            category=category,
            source_path=src,
            dest_path=dst,
            source_size=src_stat.st_size,
            dest_size=dst_stat.st_size,
            source_mtime=src_stat.st_mtime,
            dest_mtime=dst_stat.st_mtime,
        )

    # Full comparison: hash
    src_hash = _hash_file(src, algorithm)
    dst_hash = _hash_file(dst, algorithm)

    if src_hash == dst_hash:
        category = FileCategory.IDENTICAL
    else:
        category = FileCategory.CONFLICT

    return FileComparison(
        rel_path=rel_path,
        category=category,
        source_path=src,
        dest_path=dst,
        source_hash=src_hash,
        dest_hash=dst_hash,
        source_size=src_stat.st_size,
        dest_size=dst_stat.st_size,
        source_mtime=src_stat.st_mtime,
        dest_mtime=dst_stat.st_mtime,
    )


def scan_destination(
    source_files: dict[str, str | Path],
    dest_dir: str | Path,
    *,
    algorithm: str = "sha256",
    quick: bool = False,
    include_dest_only: bool = False,
) -> DestinationScanResult:
    """Scan a destination directory against a set of source files.

    This is the primary entry point for plan generation from file
    operations. Given a mapping of {rel_path: source_absolute_path},
    it compares each against the destination directory and categorizes
    the results.

    Args:
        source_files: Mapping of relative path → absolute source path.
        dest_dir: Destination directory to scan.
        algorithm: Hash algorithm for file comparison.
        quick: If True, compare size + mtime only (skip hash).
        include_dest_only: If True, also scan for files in dest_dir
            that aren't in source_files.

    Returns:
        DestinationScanResult with all comparisons categorized.
    """
    dest_dir = Path(dest_dir)
    result = DestinationScanResult()

    for rel_path, source_path in source_files.items():
        dest_path = dest_dir / rel_path
        comparison = compare_files(
            source_path, dest_path, rel_path,
            algorithm=algorithm, quick=quick,
        )
        result.comparisons.append(comparison)

    if include_dest_only:
        source_rels = set(source_files.keys())
        if dest_dir.is_dir():
            for dest_file in dest_dir.rglob("*"):
                if dest_file.is_file():
                    rel = str(dest_file.relative_to(dest_dir)).replace("\\", "/")
                    if rel not in source_rels:
                        stat = dest_file.stat()
                        result.comparisons.append(FileComparison(
                            rel_path=rel,
                            category=FileCategory.DEST_ONLY,
                            dest_path=str(dest_file),
                            dest_size=stat.st_size,
                            dest_mtime=stat.st_mtime,
                        ))

    return result
