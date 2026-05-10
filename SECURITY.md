# Security policy

## Supported versions

NetPulse is pre-1.0. Security fixes are made on `main`; older commits
are not patched. Pin to a specific commit SHA if you need stability.

## Reporting a vulnerability

If you find a security issue in NetPulse itself (the code, the
deployed service, or one of the published Docker images), please email
the maintainer directly rather than opening a public issue:

- **parth.auti1@gmail.com**

Include enough detail to reproduce: command, input, and observed
behavior. I'll acknowledge within seven days and aim to ship a fix
within thirty.

## Scope

In scope:

- Code-execution or path-traversal bugs in the Python codebase.
- Authentication / authorization bypass on the FastAPI surface.
- Vulnerabilities in how NetPulse parses external feeds (BGP MRT,
  Atlas JSON, RPKI JSON, CAIDA serial-2). External feeds are
  untrusted and the parser must not crash or escape on malicious
  input.

Out of scope:

- Issues in the upstream feeds themselves (CAIDA, RIPE NCC, Cloudflare
  RPKI, etc.). Report those to the publishers.
- Denial-of-service against the live `netpulse-pauti.fly.dev` deployment;
  the auto-stop machine policy is the documented behavior.
- Anything requiring a social-engineering vector against a maintainer.

## Out-of-scope but please tell me anyway

- Performance footguns in the ingest path.
- Misleading or unverifiable numbers in `BENCHMARK.md`.
- Citations that have rotted or that I got wrong.
