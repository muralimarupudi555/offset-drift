"""Measure what a paginated scan actually returns while the table changes under it.

`LIMIT 50 OFFSET 400` is read as "the ninth page". It is not. It is "skip four hundred
rows of whatever this query returns right now, then take fifty", and when rows have been
inserted or deleted since page eight, those are not the same four hundred rows.

Nothing errors. The page comes back the right size. Rows are quietly seen twice or never
seen at all, and the only way to find out is to count.
"""

from offset_drift.config import ConfigError, ScanConfig

__all__ = ["ScanConfig", "ConfigError"]
__version__ = "0.1.0"
