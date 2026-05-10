# Why the textbook BGP hijack detector misses the textbook BGP hijack

*Numbers are ground-truth from a live run against the RIPE RIS archive
on 2026-05-09. Project: <https://github.com/pauti04/netpulse>.*

---

I built [NetPulse][netpulse], a small open-source BGP anomaly detector,
to teach myself routing in the way I learn things best — by trying to
build something that does it. The first detector I implemented is the
one every "BGP hijack detection 101" piece walks you through: **MOAS**
— Multiple Origin AS. For each prefix you see in a window, count
distinct origin ASes; more than one means something's off.

I tested it. Worked great on synthetic data. Then I ran it against the
canonical example — the 2008 YouTube/Pakistan hijack, the textbook of
all BGP hijacks — using actual RIPE RIS archive data.

It didn't fire.

This is a short note about why, and what does work. The discovery isn't
new to working network engineers, but it surprised me, and the way it
falls out of the data is a clean story.

## What we're trying to detect

On 2008-02-24 at 18:47 UTC, AS17557 (Pakistan Telecom) announced
`208.65.153.0/24` to its upstream PCCW (AS3491), which propagated it
globally. YouTube's actual prefix at the time was `208.65.152.0/22`
from AS36561. For the next 80 minutes the more-specific `/24` won the
routing decision in any network that received both, and YouTube went dark
for chunks of the Internet.

The classical description of this incident — the one in the [RIPE NCC
case study][ripe-yt] that more than a few security textbooks quote — is:
"Pakistan Telecom announced a YouTube prefix." That phrasing is what set
me up to expect MOAS would catch it.

## What MOAS actually checks

MOAS, in the strict definition, checks whether a single prefix is being
announced by more than one origin AS. The implementation is direct:

```python
for prefix, observed_origins in features.origins_by_prefix.items():
    if len(observed_origins) > 1:
        emit_alert(prefix, observed_origins)
```

The trap is hiding in plain sight: BGP routing decisions are keyed by
**(prefix, mask)**. From the protocol's perspective, `208.65.152.0/22`
and `208.65.153.0/24` are not "the same prefix" — they are two distinct
NLRIs (Network Layer Reachability Information). A router can hold both
in its table simultaneously, and the longest-match wins for any address
in the more-specific.

## The data tells you

When I pulled one hour of RRC00 updates for 2008-02-24 18:00–19:00 UTC
and grouped by `prefix`, the only entry for `208.65.153.0/24` looked
like this:

```
208.65.153.0/24  origin_as 17557  count 27
```

No second origin. AS36561 never announced `208.65.153.0/24` because
AS36561 was announcing `208.65.152.0/22` — a different prefix. MOAS
finds nothing because there is, strictly speaking, nothing for it to
find.

If I'd squint and say "well, 208.65.152.0/22 covers 208.65.153.0/24 so
they're the *same network*," I'd be reasoning about IP space, not BGP
state. The detector operates on BGP state.

## The fix

A supernet-aware detector. Maintain a baseline mapping from prefix to
legitimate origin ASes (in production: a recent RIB; in this benchmark:
one hand-curated row sourced from the RIPE writeup). For each prefix
observed in the update window, find the most-specific supernet of that
prefix in the baseline. If the observed origin is *not* an authorized
origin for the supernet, emit an alert.

```python
for prefix, observed in features.origins_by_prefix.items():
    cover = baseline.most_specific_supernet(prefix)
    if cover is None:
        continue
    covering_prefix, legitimate = cover
    if observed - legitimate:
        emit_alert(prefix, covering=covering_prefix, unauthorized=observed - legitimate)
```

On the same data, with a one-row baseline of `208.65.152.0/22 → AS36561`,
this fires exactly once, on `208.65.153.0/24`, attributing the
unauthorized origin to AS17557 and pointing at the legit supernet.

## False-positive analysis

The worry, of course, is that the supernet-aware detector trades one
gap for a flood. To check, I pulled four background hours from the days
either side of the hijack: 2008-02-23 00:00 UTC, 2008-02-24 06:00 UTC,
2008-02-24 12:00 UTC, and 2008-02-25 00:00 UTC. Same RRC00 collector,
same one-row baseline.

```
window                                    moas  sub
2008-02-23 00:00 UTC (background)           14    0
2008-02-24 06:00 UTC (background)          145    0
2008-02-24 12:00 UTC (background)           16    0
2008-02-24 18:00 UTC (HIJACK)               10    1
2008-02-25 00:00 UTC (background)           13    0
TOTAL                                      198    1
```

Sub-prefix detector: **0 false positives across 13,961 background
prefixes**, fires once on the hijack hour. MOAS detector: ~40
alerts/hour mean. (The 06:00 UTC spike of 145 looks like a separate
anomaly somewhere in the table — worth investigating, but not a
hijack of a known prefix.)

## The honest framing

There's a temptation to lead with "detected the YouTube hijack in 3
seconds." Resist it. In the replay harness, *latency is bounded by the
chunk size you ran with*, because each chunk's expanding window is
evaluated as a unit. Smaller chunks, smaller reported latency. With
streaming detection — running the same logic on the live RIS Live
WebSocket — the alert fires when the first qualifying update arrives,
which on the Pakistan case is the AS17557 announcement at 18:47:57 UTC
itself.

The number that matters isn't latency; it's the confusion matrix. Here
that's TPR = 1/1 and FPR = 0/13961 over the surveyed window. Neither is
asymptotic — both come from one hijack and a few hours of background —
but both are observable on real data, with reproducible commands.

## Lessons that fall out

1. **The textbook framing is sometimes a category error.** "Pakistan
   Telecom announced a YouTube prefix" sounds like one event. From
   BGP's view it was a *new* prefix, not a duplicate of YouTube's, and
   that distinction is what makes detection non-trivial.

2. **MOAS isn't broken — it's a primitive.** It correctly flags
   multi-origin announcements, of which there are many in normal
   operation (anycast, multi-homed customers). It's just not, by
   itself, a hijack detector.

3. **Real data finds things synthetic tests don't.** A purely-synthetic
   test would have been delighted with the MOAS detector — a
   "two-origin scenario" is exactly what fires it. The category error
   only shows up when you replay against records that BGP actually saw.

4. **"Honest evaluation" needs background hours.** A single TPR is
   suggestive; a TPR plus an FPR over multiple hours is testimony.

## What's next, briefly

NetPulse extends past this discovery. The same project also implements
RFC 7908 valley-free route-leak detection (against CAIDA's serial-2
inferred AS relationships), RFC 6811 RPKI Origin Validation, and a
small **multi-signal correlator** that binds BGP alerts to RIPE Atlas
latency anomalies. On the **2018-11-12 MainOne → Google route leak**
the BGP route-leak detector emits 1,985 leak-shape alerts on the real
archive paths *and* Atlas median RTT to `8.8.8.8` jumps from 38.0 ms
baseline to 49.9 ms during the leak window — exactly the period when
Google traffic was getting rerouted through Nigeria, China, and Russia.
Those two signals fuse into a single critical alert, and the
reproduction is a 100-line script in the repo.

If you want to play with this, the project is at
<https://github.com/pauti04/netpulse>; `uv run netpulse demo` runs the
YouTube case against a bundled fixture in under a second, no setup.

[netpulse]: https://github.com/pauti04/netpulse
[ripe-yt]: https://www.ripe.net/publications/news/youtube-hijacking-a-ripe-ncc-ris-case-study/
