# Contract: Health Check

**Requirements**: FR-025, FR-026, FR-027, FR-028 | **Success criteria**:
SC-006, SC-007 | **User story**: 4

---

## `GET /health/`

Reports whether the platform and each of its dependencies are reachable.

**Authentication**: none. This is the only unauthenticated endpoint in the
platform (FR-025), so container orchestration and future monitoring can reach it
without credentials.

**Request**: no parameters, no body, no headers required.

---

### Response — all dependencies reachable

**Status**: `200 OK`

```json
{
  "status": "healthy",
  "checks": {
    "database": { "status": "ok" },
    "cache": { "status": "ok" }
  }
}
```

### Response — database unreachable

**Status**: `503 Service Unavailable`

```json
{
  "status": "unhealthy",
  "checks": {
    "database": { "status": "error" },
    "cache": { "status": "ok" }
  }
}
```

### Response — cache unreachable

**Status**: `503 Service Unavailable`

```json
{
  "status": "unhealthy",
  "checks": {
    "database": { "status": "ok" },
    "cache": { "status": "error" }
  }
}
```

Both unreachable: `503` with both `checks` entries set to `error`.

---

## Behavioural contract

**Machine-detectable outcome (FR-027)**: the HTTP status code is the signal.
`200` means healthy, `503` means unhealthy. A supervisor never has to parse the
body to make a restart decision. The body exists to identify *which* dependency
failed (FR-026).

**Bounded response time (FR-027, SC-006)**: each probe carries its own
2-second timeout — Postgres via `connect_timeout`, Redis via
`socket_connect_timeout`/`socket_timeout`. Worst case is roughly 4 seconds,
inside SC-006's 5-second bound. A hung or partitioned dependency produces a
definite `503`, never a hang and never a `500`.

**Never a 500**: any exception raised by a probe is caught and converted to that
dependency's `error` status. An unhandled `500` would be indistinguishable from
an application crash and would violate FR-027's "distinct machine-detectable
outcome rather than an unhandled error."

**Independent probes**: a failing database probe does not short-circuit the
cache probe. Both always run, so a single response identifies every failing
dependency (SC-007).

---

## Disclosure constraints (FR-028)

The response body is exactly the three-key structure above. It MUST NOT contain:

- host names, IP addresses, ports, or connection strings
- database or cache credentials, or any environment variable value
- Django, Python, Postgres, or Redis version strings
- exception messages, tracebacks, driver class names, or SQL
- request counts, uptime, or any other operational telemetry

Failure detail is written to the server log, where it is available to an
operator with server access and to nobody else.

`DEBUG` must be `False` in any configuration where this endpoint is reachable by
an untrusted caller — Django's debug error pages disclose settings, which would
defeat this constraint regardless of the view's own discipline.

---

## Audit

None. Health queries are not recorded — they are unauthenticated, high-frequency
liveness probes with no actor and no affected record, and logging them would
flood the audit table that Principle II reserves for actions against business
data.

---

## Container integration

`docker-compose.yml` uses this endpoint as the `web` service's healthcheck, so
"the application is up" in Story 1 is machine-verified rather than asserted:

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/').status==200 else 1)"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

The check uses the container's own Python rather than assuming `curl` is present
in the slim base image.
