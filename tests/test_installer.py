from __future__ import annotations

from pathlib import Path

from agentic_orchestrator.installer import install_sibling_tools, render_install_report_text


def test_install_siblings_dry_run_writes_config(tmp_path: Path) -> None:
    install_root = tmp_path / "tools"
    config_path = tmp_path / "config.local.toml"

    report = install_sibling_tools(
        install_root=str(install_root),
        write_config=str(config_path),
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert report["written_config"] == str(config_path.resolve())
    assert len(report["tools"]) == 4
    tool_names = [tool["tool"] for tool in report["tools"]]
    assert tool_names == [
        "agentic_devdocs",
        "agentic_indexer",
        "agentic_sitemap",
        "agentic_debug",
    ]
    generated = config_path.read_text(encoding="utf-8")
    assert 'command = "' + str((install_root / "agentic_debug" / "bin" / "moodle-debug").resolve()) + '"' in generated
    assert "# devdocs_db_path =" in generated


def test_install_siblings_runner_executes_expected_commands(tmp_path: Path) -> None:
    install_root = tmp_path / "tools"
    install_root.mkdir()
    seen: list[tuple[list[str], str]] = []

    def runner(command: list[str], workdir: str) -> None:
        seen.append((command, workdir))
        if command[:4] == ["git", "clone", "https://github.com/mattporritt/agentic_devdocs", str(install_root / "agentic_devdocs")]:
            (install_root / "agentic_devdocs").mkdir()
        elif command[:4] == ["git", "clone", "https://github.com/mattporritt/agentic_indexer", str(install_root / "agentic_indexer")]:
            (install_root / "agentic_indexer").mkdir()
        elif command[:4] == ["git", "clone", "https://github.com/mattporritt/agentic_sitemap", str(install_root / "agentic_sitemap")]:
            (install_root / "agentic_sitemap").mkdir()
        elif command[:4] == ["git", "clone", "https://github.com/mattporritt/agentic_debug", str(install_root / "agentic_debug")]:
            (install_root / "agentic_debug").mkdir()

    report = install_sibling_tools(
        install_root=str(install_root),
        install_sitemap_browser=False,
        runner=runner,
    )

    assert report["dry_run"] is False
    assert any(command[0] == "git" and "agentic_devdocs" in command[2] for command, _ in seen)
    assert any(command[:3] == [str(Path(__import__("sys").executable)), "-m", "venv"] for command, _ in seen)
    assert any(command[:3] == [".venv/bin/pip", "install", "-e"] for command, _ in seen)
    assert any(command[:2] == ["composer", "install"] for command, _ in seen)
    assert not any(command[:3] == [".venv/bin/playwright", "install", "chromium"] for command, _ in seen)


def test_render_install_report_text_includes_written_config(tmp_path: Path) -> None:
    report = {
        "install_root": str(tmp_path),
        "dry_run": True,
        "install_sitemap_browser": True,
        "tools": [
            {
                "tool": "agentic_devdocs",
                "repo_url": "https://github.com/mattporritt/agentic_devdocs",
                "repo_dir": str(tmp_path / "agentic_devdocs"),
                "command_path": str(tmp_path / "agentic_devdocs" / ".venv" / "bin" / "agentic-docs"),
                "clone_status": "would_clone",
                "install_commands": [],
            }
        ],
        "written_config": str(tmp_path / "config.local.toml"),
    }

    rendered = render_install_report_text(report)
    assert "Sibling Tool Install" in rendered
    assert "agentic_devdocs: would_clone" in rendered
    assert "Config written:" in rendered
