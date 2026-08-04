# Standalone bundle

For sites without an existing Prometheus/Grafana stack, the
[`deploy/`](https://github.com/amitpatole/latenzy/tree/main/deploy)
docker-compose bundle runs the prober, Prometheus, and Grafana with the
[dashboard](dashboards.md) and rules pre-provisioned.

```bash
cd deploy
mkdir -p secrets && openssl rand -hex 32 > secrets/latenzy_token
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...
export GRAFANA_ADMIN_PASSWORD=...   # no default password ships with the bundle
docker compose up -d
```

Grafana serves the comparison dashboard read-only at `http://localhost:3000`
(loopback-published only). Prometheus is at `http://localhost:9090`.

## What the bundle does for you

- Builds the prober image and runs it behind the compose network, exposing
  `/metrics` only inside the network, gated by the bearer token.
- Provisions the Prometheus datasource and the dashboard into Grafana from the
  repo's `dashboards/` and `prometheus/` directories — the bundled and published
  copies cannot drift.
- Ships **no default secrets**: Grafana refuses to start without
  `GRAFANA_ADMIN_PASSWORD`, and the exporter token comes from the
  `secrets/latenzy_token` file you generate.

## Security notes

- Container images are pinned by digest; the prober runs as a non-root user.
- Prometheus and Grafana UIs publish to loopback only.
- Inside the compose network the exporter binds `0.0.0.0`, so the token is
  mandatory (latenzy refuses to start otherwise). See [Security](security.md).
