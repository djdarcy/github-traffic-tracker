"""preserve_lib — File preservation with manifests, verification, and metadata.

Ported from preservelib (C:\\code\\preserve\\preservelib) as a DazzleLib
candidate.  Provides manifest-tracked, hash-verified, metadata-preserving
file operations that serve as the executor backend for plan_lib.

Canonical types (FileCategory, ConflictResolution) live in core_lib —
preserve_lib imports them from there rather than defining its own copies.

Modules:
    destination   — Scan + compare source vs destination
    manifest      — Operation manifests (file list + hashes + metadata)
    operations    — Copy/move/verify/restore orchestration
    verification  — Post-op hash verification, three-way compare
    metadata      — File metadata collection/application
    links         — Cross-platform junction/symlink/hardlink handling
    pathutils     — Path analysis, pattern detection
    restore       — Restore files from manifests
    dazzlelink    — Lazy-restore via .dazzlelink sidecar files
"""

import logging

logger = logging.getLogger(__name__)

# --- Core types (from core_lib, re-exported for convenience) ---------------
from ghtraf.lib.core_lib.types import FileCategory, ConflictResolution

# --- Manifest & hashing ---------------------------------------------------
from .manifest import (
    PreserveManifest,
    calculate_file_hash,
    verify_file_hash,
    create_manifest_for_path,
    read_manifest,
)

# --- High-level operations -------------------------------------------------
from .operations import (
    copy_operation,
    move_operation,
    verify_operation,
    restore_operation,
)

# --- Metadata --------------------------------------------------------------
from .metadata import (
    collect_file_metadata,
    apply_file_metadata,
    compare_metadata,
)

# --- Restore ---------------------------------------------------------------
from .restore import (
    restore_file_to_original,
    restore_files_from_manifest,
    find_restoreable_files,
)

# --- Verification ----------------------------------------------------------
from .verification import (
    VerificationStatus,
    FileVerificationResult,
    VerificationResult,
    verify_file_against_manifest,
    verify_files_against_manifest,
    find_and_verify_manifest,
)

# --- Destination scanning --------------------------------------------------
from .destination import (
    FileComparison,
    DestinationScanResult,
    compare_files,
    scan_destination,
)

__all__ = [
    # Core types (canonical in core_lib)
    'FileCategory',
    'ConflictResolution',
    # Manifest
    'PreserveManifest',
    'calculate_file_hash',
    'verify_file_hash',
    'create_manifest_for_path',
    'read_manifest',
    # Operations
    'copy_operation',
    'move_operation',
    'verify_operation',
    'restore_operation',
    # Metadata
    'collect_file_metadata',
    'apply_file_metadata',
    'compare_metadata',
    # Restore
    'restore_file_to_original',
    'restore_files_from_manifest',
    'find_restoreable_files',
    # Verification
    'VerificationStatus',
    'FileVerificationResult',
    'VerificationResult',
    'verify_file_against_manifest',
    'verify_files_against_manifest',
    'find_and_verify_manifest',
    # Destination scanning
    'FileComparison',
    'DestinationScanResult',
    'compare_files',
    'scan_destination',
]
