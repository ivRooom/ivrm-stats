from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def load_collector() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[3]
        / "deploy"
        / "status-api"
        / "collect-minecraft-runtime.py"
    )
    spec = importlib.util.spec_from_file_location("minecraft_runtime_collector", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_collector()


def inspect_payload(
    *,
    status: str,
    running: bool,
    health: str | None = None,
    env: list[str] | None = None,
    mounts: list[dict[str, Any]] | None = None,
    exit_code: int = 0,
    oom_killed: bool = False,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "Status": status,
        "Running": running,
        "ExitCode": exit_code,
        "OOMKilled": oom_killed,
    }
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "State": state,
        "Config": {"Env": env or []},
        "Mounts": mounts or [],
    }


def test_running_main_is_started() -> None:
    server = collector.public_server(
        server_id="mc-main",
        name="生活鯖",
        role="main",
        connection="mc.ivrm.jp",
        inspect=inspect_payload(
            status="running",
            running=True,
            health="healthy",
            env=["VERSION=26.1.2", "MAX_MEMORY=4G"],
        ),
        available_mb=5_981,
    )

    assert server["runtimeStatus"] == "running"
    assert server["startability"] == "started"
    assert server["startable"] is True
    assert server["version"] == "26.1.2"


def test_sleeping_resource_with_router_is_startable(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    resource = inspect_payload(
        status="exited",
        running=False,
        env=["VERSION=26.1.2", "MAX_MEMORY=4G"],
        mounts=[{"Type": "bind", "Source": str(data), "Destination": "/data"}],
    )
    router = inspect_payload(
        status="running",
        running=True,
        env=["AUTO_SCALE_UP=true"],
        mounts=[
            {
                "Type": "bind",
                "Source": "/var/run/docker.sock",
                "Destination": "/var/run/docker.sock",
            }
        ],
    )

    server = collector.public_server(
        server_id="mc-resource",
        name="資源鯖",
        role="resource",
        connection="mc.ivrm.jp:25999",
        inspect=resource,
        router=router,
        available_mb=5_981,
    )

    assert server["runtimeStatus"] == "sleeping"
    assert server["startability"] == "startable"
    assert server["autoScaleUp"] is True
    assert "自動起動" in server["reason"]


def test_resource_is_unavailable_when_memory_is_insufficient(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    resource = inspect_payload(
        status="exited",
        running=False,
        env=["MAX_MEMORY=4G"],
        mounts=[{"Type": "bind", "Source": str(data), "Destination": "/data"}],
    )

    server = collector.public_server(
        server_id="mc-resource",
        name="資源鯖",
        role="resource",
        connection="mc.ivrm.jp:25999",
        inspect=resource,
        router=None,
        available_mb=4_500,
    )

    assert server["runtimeStatus"] == "stopped"
    assert server["startability"] == "unavailable"
    assert server["startable"] is False


def test_memory_parser_supports_gigabytes_and_megabytes() -> None:
    assert collector.parse_memory_mb("4G") == 4_096
    assert collector.parse_memory_mb("2048M") == 2_048
