from pathlib import Path

from harness.product_init import init_workspace


def test_init_workspace_creates_runtime_folders(tmp_path: Path):
    init_workspace(tmp_path)

    assert (tmp_path / "proposals" / "example_read.json").exists()
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "reports").is_dir()
    assert (tmp_path / "evidence").is_dir()
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "builder_sessions").exists()
    assert not (tmp_path / "workflows" / "example.yaml").exists()
    assert not (tmp_path / "__init__.py").exists()
