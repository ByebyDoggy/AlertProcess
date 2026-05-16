from pathlib import Path


def test_legacy_nodes_directory_has_been_removed():
    alert_processor_root = Path(__file__).resolve().parents[2]

    assert not (alert_processor_root / "nodes").exists()
