# Why MOAS doesn't catch the YouTube hijack

A short note on a subtle thing that surprised me building the BGP detector
for NetPulse: **a same-prefix multi-origin (MOAS) check cannot detect the
canonical 2008 YouTube /24 sub-prefix hijack**, even though "multiple ASes
announcing the same prefix" is the textbook description of a hijack.

## What MOAS is, and what it isn't

MOAS = Multiple Origin AS. The check is straightforward: for each prefix
seen in a window, count distinct origin ASNs in the as-paths. More than
one → flag. This is what most "BGP anomaly detection 101" material walks
you through, and it's what I implemented first
(`src/netpulse/detectors/moas.py`).

The thing the textbook framing glosses over: BGP routing decisions are
keyed by **(prefix, mask)**. `208.65.152.0/22` and `208.65.153.0/24` are
two different prefixes from BGP's perspective, even though one CIDR is
contained inside the other.

## What the YouTube hijack actually looked like

On 2008-02-24, AS17557 announced `208.65.153.0/24`. The
legitimate YouTube announcement at the time was `208.65.152.0/22` from
AS36561 — a less-specific prefix. AS17557 didn't claim YouTube's
prefix; it announced a more-specific subset of it.

Routers prefer more-specifics, so AS17557's `/24` won the routing decision
end-to-end across networks that received the announcement. YouTube's `/22`
was still in everyone's table — it was just the wrong best path for IPs
inside the hijacked `/24`.

In our pulled hour (RRC00, 2008-02-24 18:00–19:00 UTC):

```
208.65.153.0/24 → origin_as 17557        (27 records, 5 distinct peers)
208.65.152.0/22 → not present in updates (it was already in the RIB,
                                          unchanged through this hour)
```

A MOAS check on `208.65.153.0/24` sees `{17557}` and finds nothing wrong.
A MOAS check on `208.65.152.0/22` sees `{36561}` (or nothing, if outside
its data) and finds nothing wrong. The two prefixes never collide on the
MOAS check because they have different masks.

## What actually catches it

A detector with a notion of **what supernet covers each new
more-specific** does. Concretely:

1. Maintain a baseline mapping from prefix to legitimate origin
   ASNs — typically loaded from a recent RIB.
2. For each prefix observed in the update window, find the most-specific
   supernet of that prefix in the baseline.
3. If the observed origin is *not* an authorized origin for the supernet,
   raise an alert.

That's `SubPrefixHijackDetector` (`src/netpulse/detectors/subprefix.py`).
On the same data, with a one-row baseline of
`208.65.152.0/22 → AS36561`, it fires exactly once on `208.65.153.0/24`,
attributing the unauthorized origin to AS17557 and pointing at the legit
supernet.

## Why this matters for the benchmark

This was the first concrete proof that NetPulse's "the differentiator is
honest evaluation" framing isn't just rhetoric. A purely-synthetic test
would have been happy with the MOAS detector — "hijack scenario, two
origins on a prefix, MOAS fires, ship it." Running the actual archive
shows the textbook hijack does not match the textbook detection, and that
the distinction is load-bearing.

It's also a good cautionary note when reading other "we detect hijacks"
write-ups: ask which kinds, and against what data. MOAS is fine for
same-prefix attacks (which do happen — typo-style fat-fingers, leaks via
unfiltered customers), but a supernet-aware check is required for the
sub-prefix family that includes most of the famous incidents.

## Numbers

Reproducible end-to-end with the commands in
[`BENCHMARK.md`](../BENCHMARK.md). With one labeled incident:

- 1/1 detected
- 3.0 s latency from documented onset (1-minute replay chunks)
- 0 false positives in the surrounding hour
- 10 unrelated MOAS alerts in the same hour — all on multi-homed or
  anycast prefixes, consistent with operational reality
