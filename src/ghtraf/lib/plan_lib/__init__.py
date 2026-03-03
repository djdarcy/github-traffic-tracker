"""
plan_lib — Plan-execute architecture with dependency resolution.

Provides the execution engine and rendering for plans built from core_lib types.
Consumer applications create plans using Action/Plan from core_lib, then execute
them via execute_plan() with a custom executor_fn.

Public API:
    execute_plan          — execute a plan with dependency resolution + error policy
    DefaultTextRenderer   — color-coded text plan renderer (THAC0 integration)
    FileComparison        — result of comparing source vs destination file
    DestinationScanResult — categorized scan of destination directory
    compare_files         — compare two files by hash or quick (size+mtime)
    scan_destination      — scan dest dir against source file mapping
"""

from .executor import execute_plan
from .renderer import DefaultTextRenderer
from .file_ops import (
    FileComparison,
    DestinationScanResult,
    compare_files,
    scan_destination,
)

__all__ = [
    'execute_plan',
    'DefaultTextRenderer',
    'FileComparison',
    'DestinationScanResult',
    'compare_files',
    'scan_destination',
]
