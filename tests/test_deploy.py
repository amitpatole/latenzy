"""Drift guards for the Grafana/Prometheus artifacts and the compose bundle:
dashboards must be valid and importable, rules must be well-formed and reference
latenzy metrics, and the bundle must never ship a default secret."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from latenzy.config import load_config

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = sorted((ROOT / "dashboards").glob("*.json"))
METRIC_RE = re.compile(r"\blatenzy[_:]")


def _share_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "share_dashboard", ROOT / "scripts" / "share_dashboard.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _targets(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for panel in dashboard["panels"] for t in panel.get("targets", [])]


def test_dashboards_exist() -> None:
    assert DASHBOARDS, "no dashboard JSON files found"


def test_dashboards_are_valid_and_importable() -> None:
    for path in DASHBOARDS:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        assert dashboard["uid"], path.name
        assert dashboard["title"].startswith("latenzy"), path.name
        assert "latenzy" in dashboard["tags"], path.name
        # A datasource template variable makes the JSON work both provisioned
        # (compose bundle) and imported from the Grafana dashboard library.
        variables = {v["name"]: v for v in dashboard["templating"]["list"]}
        assert variables["datasource"]["type"] == "datasource", path.name
        for panel in dashboard["panels"]:
            assert panel["datasource"]["uid"] == "${datasource}", (path.name, panel["title"])


def test_dashboard_queries_reference_latenzy_metrics() -> None:
    for path in DASHBOARDS:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        targets = _targets(dashboard)
        assert targets, path.name
        for target in targets:
            assert METRIC_RE.search(target["expr"]), (path.name, target["expr"])


def test_recording_rules_well_formed() -> None:
    data = yaml.safe_load((ROOT / "prometheus" / "recording_rules.yml").read_text())
    rules = [rule for group in data["groups"] for rule in group["rules"]]
    assert rules
    for rule in rules:
        assert rule["record"].startswith("latenzy:"), rule
        assert METRIC_RE.search(rule["expr"]), rule


def test_alert_rules_well_formed() -> None:
    data = yaml.safe_load((ROOT / "prometheus" / "alert_rules.yml").read_text())
    rules = [rule for group in data["groups"] for rule in group["rules"]]
    assert rules
    for rule in rules:
        assert rule["alert"].startswith("Latenzy"), rule
        assert METRIC_RE.search(rule["expr"]), rule
        assert rule["labels"]["severity"] in {"warning", "critical"}, rule
        assert "summary" in rule["annotations"], rule


def test_dashboards_only_use_defined_recording_rules() -> None:
    data = yaml.safe_load((ROOT / "prometheus" / "recording_rules.yml").read_text())
    defined = {rule["record"] for group in data["groups"] for rule in group["rules"]}
    for path in DASHBOARDS:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for target in _targets(dashboard):
            for used in re.findall(r"latenzy:[a-z0-9_:]+", target["expr"]):
                assert used in defined, (path.name, used)


def test_share_dashboards_in_sync_with_provisioned() -> None:
    # grafana.com uploads use the generated "export for sharing externally"
    # form in dashboards-share/; regenerate with scripts/share_dashboard.py.
    share = _share_module()
    for path in DASHBOARDS:
        committed = (ROOT / "dashboards-share" / path.name).read_text(encoding="utf-8")
        rendered = share.render(json.loads(path.read_text(encoding="utf-8")))
        assert committed == rendered, f"{path.name}: stale share copy, regenerate"


def test_share_dashboards_are_share_format() -> None:
    for path in sorted((ROOT / "dashboards-share").glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        dashboard = json.loads(raw)
        assert dashboard["id"] is None, path.name
        assert dashboard["__inputs"][0]["name"] == "DS_PROMETHEUS", path.name
        assert {r["type"] for r in dashboard["__requires"]} >= {"grafana", "datasource"}
        assert "${datasource}" not in raw, path.name
        assert "datasource" not in [v["name"] for v in dashboard["templating"]["list"]]


def test_compose_bundle_fails_closed() -> None:
    raw = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(raw)
    assert set(compose["services"]) == {"latenzy", "prometheus", "grafana"}
    # No default admin password: the :? form makes compose refuse to start.
    assert "${GRAFANA_ADMIN_PASSWORD:?" in raw
    # Exporter token comes from a local secrets file, never a committed value.
    assert compose["secrets"]["latenzy_token"]["file"] == "./secrets/latenzy_token"
    for service in ("latenzy", "prometheus"):
        assert "latenzy_token" in compose["services"][service]["secrets"]
    # Prometheus and Grafana UI ports stay loopback-published.
    assert compose["services"]["prometheus"]["ports"] == ["127.0.0.1:9090:9090"]
    assert compose["services"]["grafana"]["ports"] == ["127.0.0.1:3000:3000"]


def test_bundle_prober_config_requires_auth() -> None:
    config = load_config(ROOT / "deploy" / "latenzy.yaml")
    # 0.0.0.0 bind inside the compose network — the token must be configured
    # or latenzy refuses to start (pinned by test_exporter fail-closed tests).
    assert config.exporter.host == "0.0.0.0"
    assert config.exporter.auth_token_env == "LATENZY_TOKEN"


def test_dockerignore_excludes_secrets_from_build_context() -> None:
    # Build context is the repo root; without these excludes COPY . would bake
    # deploy/secrets/latenzy_token (and any local .env) into an image layer.
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for needed in ("deploy/secrets/", "secrets/", ".env", ".venv/", ".git/"):
        assert needed in ignore, f".dockerignore missing {needed!r}"


def test_bundle_images_pinned_by_digest() -> None:
    compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text())
    for service in ("prometheus", "grafana"):
        image = compose["services"][service]["image"]
        assert "@sha256:" in image, f"{service} image not digest-pinned: {image}"


def test_bundle_mounts_repo_dashboards_and_rules() -> None:
    compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text())
    grafana_mounts = compose["services"]["grafana"]["volumes"]
    assert "../dashboards:/var/lib/grafana/dashboards:ro" in grafana_mounts
    prometheus_mounts = compose["services"]["prometheus"]["volumes"]
    assert "../prometheus:/etc/prometheus/rules:ro" in prometheus_mounts
