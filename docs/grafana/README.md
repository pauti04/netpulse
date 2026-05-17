# Grafana dashboard

`netpulse-dashboard.json` is a ready-to-import Grafana 10+ dashboard
for NetPulse's `/metrics` endpoint. Drop it into any Grafana instance
with a Prometheus datasource that scrapes the NetPulse deployment.

## What it shows

- **Requests / sec, by endpoint** — `rate(netpulse_requests_total[5m])`,
  legend keyed by the `detector` label (the FastAPI endpoint name).
- **Alerts emitted / sec, by detector** —
  `rate(netpulse_alerts_total[5m])`, legend keyed by the detector
  that fired.
- **Baseline prefixes** — `netpulse_baseline_prefixes` as a stat.
  Reports the sub-prefix supernet count the deployment loaded at
  startup. Non-zero confirms the sub-prefix detector is wired.
- **Total requests served** — `sum(netpulse_requests_total)`.
- **Cumulative alerts by detector** — bargauge of
  `netpulse_alerts_total`, one row per detector.

The dashboard uses a `${datasource}` template variable so import
chooses any Prometheus datasource without editing the file.

## Wiring Prometheus to a live NetPulse

The default scrape config for a Fly.io / local deployment:

```yaml
scrape_configs:
  - job_name: netpulse
    metrics_path: /metrics
    static_configs:
      - targets:
          - netpulse-pauti.fly.dev:443
        labels:
          deployment: fly
    scheme: https
```

For a localhost deployment use `localhost:8000` and `scheme: http`.

## Import

1. Grafana → Dashboards → New → Import.
2. Upload `netpulse-dashboard.json` or paste its content.
3. Pick the Prometheus datasource.
4. Save.

Custom panels for `netpulse_alerts_total` by individual detector
(`subprefix_hijack`, `route_leak`, `customer_cone_leak`, `moas`,
`withdraw_spike`, `rpki_invalid`) can be added by duplicating the
"Cumulative alerts" panel and filtering with
`netpulse_alerts_total{detector="<name>"}`.
