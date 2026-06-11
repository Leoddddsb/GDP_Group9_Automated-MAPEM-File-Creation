"""Evidence fusion stage: mapped_evidence.json -> nested MAPEM model + report."""
from .fuse import fuse, parse_path, set_nested, CONSISTENCY_RULES

__all__ = ["fuse", "parse_path", "set_nested", "CONSISTENCY_RULES"]
