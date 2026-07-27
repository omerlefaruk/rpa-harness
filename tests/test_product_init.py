from pathlib import Path

from harness.product_init import init_workspace


def test_init_workspace_creates_agent_ready_folder(tmp_path: Path):
    init_workspace(tmp_path)

    assert (tmp_path / "proposals" / "example_read.json").exists()
    assert (tmp_path / "config" / "default.yaml").exists()
    assert (tmp_path / ".agents" / "config" / "agent_command_manifest.json").exists()
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "runs").is_dir()
    assert (tmp_path / "reports").is_dir()
    assert (tmp_path / "evidence").is_dir()
    assert not (tmp_path / "builder_sessions").exists()
    assert not (tmp_path / "workflows" / "example.yaml").exists()
    assert not (tmp_path / "__init__.py").exists()
