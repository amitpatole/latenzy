"""Derive grafana.com-uploadable "export for sharing externally" dashboards
from the provisioned JSON in dashboards/.

The provisioned form (datasource template variable) is what the compose bundle
mounts; grafana.com's upload validator expects the share form (__inputs /
__requires, id: null). One source, two representations — regenerate with:

    uv run python scripts/share_dashboard.py

A drift-guard test regenerates in-process and fails if the committed share
copies are stale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS_DIR = ROOT / "dashboards"
# Sibling of dashboards/, NOT inside it: the compose bundle mounts dashboards/
# into Grafana's file provisioner, which scans subdirectories — a share copy in
# there would be provisioned as a duplicate uid with an unresolvable datasource.
SHARE_DIR = ROOT / "dashboards-share"

GRAFANA_VERSION = "11.1.0"


def _swap_datasource_refs(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _swap_datasource_refs(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_swap_datasource_refs(v) for v in node]
    if node == "${datasource}":
        return "${DS_PROMETHEUS}"
    return node


def _panel_types(dashboard: dict[str, Any]) -> list[str]:
    return sorted({panel["type"] for panel in dashboard["panels"]})


def to_share_format(dashboard: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = _swap_datasource_refs(json.loads(json.dumps(dashboard)))
    out["templating"]["list"] = [
        var for var in out["templating"]["list"] if var["name"] != "datasource"
    ]
    out["__inputs"] = [
        {
            "name": "DS_PROMETHEUS",
            "label": "Prometheus",
            "description": "Prometheus datasource scraping the latenzy exporter",
            "type": "datasource",
            "pluginId": "prometheus",
            "pluginName": "Prometheus",
        }
    ]
    out["__elements"] = {}
    out["__requires"] = [
        {"type": "grafana", "id": "grafana", "name": "Grafana", "version": GRAFANA_VERSION},
        {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"},
        *(
            {"type": "panel", "id": panel_type, "name": panel_type, "version": ""}
            for panel_type in _panel_types(out)
        ),
    ]
    out["annotations"] = {
        "list": [
            {
                "builtIn": 1,
                "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                "enable": True,
                "hide": True,
                "iconColor": "rgba(0, 211, 255, 1)",
                "name": "Annotations & Alerts",
                "type": "dashboard",
            }
        ]
    }
    out["id"] = None
    out["links"] = []
    out["liveNow"] = False
    out["refresh"] = "1m"
    out["fiscalYearStartMonth"] = 0
    out["weekStart"] = ""
    out["timepicker"] = {}
    out["version"] = 1
    return {key: out[key] for key in sorted(out)}


def render(dashboard: dict[str, Any]) -> str:
    return json.dumps(to_share_format(dashboard), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    SHARE_DIR.mkdir(exist_ok=True)
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        target = SHARE_DIR / path.name
        target.write_text(render(json.loads(path.read_text(encoding="utf-8"))), encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
