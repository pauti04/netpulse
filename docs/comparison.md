# Comparison with prior work

A short note on how NetPulse's detection signals stack up against the
established open-source / academic systems most operators look at first.
This isn't a head-to-head benchmark — those would need running every tool
on the same incident corpus, which is a paper, not a README. It's the
context a reader needs to know whether NetPulse is solving a problem the
state of the art already solved.

## ARTEMIS

[ARTEMIS][artemis] (Sermpezis, Kotronis, Dainotti, Kostoulas et al.,
*Neutralizing BGP Hijacking Within a Minute*, IEEE/ACM ToN 2018) is
the canonical comparison. It is both more ambitious and significantly
heavier than NetPulse:

| Aspect                     | ARTEMIS                                        | NetPulse                                                     |
| -------------------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| Architecture               | Containerized multi-component service          | Single Python package, CLI-driven                            |
| Data sources               | BGPStream (RIPE RIS + RouteViews) + RIPE Atlas + ExaBGP local feeds | BGPStream (one collector) + RIPE Atlas (one measurement)     |
| Ground truth               | Network-operated config: ASN list, prefix list, RPKI ROAs | One-row hand-curated baseline per incident, RPKI not yet integrated |
| Hijack types covered       | Type 0/1 origin, Type N (path), squatting       | Sub-prefix origin (one detector), MOAS primitive             |
| Mitigation                 | Automatic ROA filtering / outsourcing announcement | Detection only; mitigation out of scope                      |
| Detection latency (paper)  | < 60 s end-to-end on tested incidents          | Bounded by replay chunk size in archive replay; first-update under streaming |
| Public benchmark numbers   | Several incidents in the paper, plus IRR-grounded synthetic | One labeled incident + 4-hour FPR survey on real archive data |

**The gap:** ARTEMIS detects more hijack types and has a real mitigation
loop. **The overlap:** the streaming sub-prefix detection logic is the
same shape; running NetPulse's `subprefix_hijack` on the YouTube fixture
gives the same correctness story ARTEMIS does on its own paper-cited
runs.

**Honest comparison would require:** running ARTEMIS against the YouTube
hour with a comparable baseline and reporting both tools' alerts side
by side. That's open work.

## BGPmon / Cisco Crosswork BGP Tools (closed)

Operator-facing alerting service; not benchmarkable from outside. Cited
historically as the source of public BGP-incident notifications (e.g.,
the YouTube event was reported via BGPmon's now-shuttered alerting
within minutes). NetPulse does not try to replicate the global operator
network, but the detector ships with the same TPR=1 the BGPmon notice
implied for that incident.

## Cloudflare Radar

[Radar][radar] is a public dashboard, not a detector. It surfaces
incidents Cloudflare has labeled, with prefix/AS context. NetPulse uses
Radar as a *source* of recent labeled incidents (e.g., the 2024-06-27
1.1.1.1/32 hijack we plan to add to the fixture set), not as a tool to
compare against.

## bgp.tools / RIPEstat

Both are inspection tools — query the table, view a prefix's history.
Operationally indispensable, but not detectors in the streaming sense.
NetPulse's `netpulse stream` is closest in spirit to RIPEstat's
"Looking Glass" feeds, with detector logic on top.

## Where NetPulse fits

The slot NetPulse aims at is **honest, reproducible evaluation of small
detector ideas against real archive data**. ARTEMIS is the right answer
when you have a network to defend; NetPulse is the right answer when
you want to write a paper, blog post, or thesis chapter that says "I
tried detector X on incident Y and got Z" with reproduction commands a
reader can rerun in five minutes.

That slot is open in the public toolchain, and it's the framing under
which the headline numbers in [`BENCHMARK.md`](../BENCHMARK.md) are
worth their length.

[artemis]: https://github.com/FORTH-ICS-INSPIRE/artemis
[radar]: https://radar.cloudflare.com/
