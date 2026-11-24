from pathlib import Path

from global_library_mcp.registry import Registry


def test_registry_contains_phase_zero_candidates():
    registry = Registry(Path(__file__).parents[1] / "libraries.yaml")
    assert registry.get("loc")
    assert registry.get("ndl")
    assert registry.get("gallica")
    assert registry.get("tw-ncl")["capabilities"]["ocr"] == "unknown"
