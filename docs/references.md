# References

The detection rules and data formats here come from operator practice and
standards. This file is the bibliography you'd normally see at the end of a
paper. Where possible, primary sources are linked; the BGP RFCs are the
ground truth for protocol behavior.

## Standards

- **RFC 4271** — *A Border Gateway Protocol 4 (BGP-4)*. Y. Rekhter, T. Li,
  S. Hares (eds), 2006. <https://www.rfc-editor.org/rfc/rfc4271>. The
  protocol; defines what an UPDATE message is, what `as-path` and
  community attributes look like, what a withdraw is.
- **RFC 6480** — *An Infrastructure to Support Secure Internet Routing*.
  M. Lepinski, S. Kent, 2012. <https://www.rfc-editor.org/rfc/rfc6480>.
  RPKI: a stronger basis than RIB-derived baselines; not yet used here.
- **RFC 7908** — *Problem Definition and Classification of BGP Route
  Leaks*. K. Sriram et al., 2016. <https://www.rfc-editor.org/rfc/rfc7908>.
  Taxonomy used by the route-leak detector.
- **RFC 8893** — *Resource Public Key Infrastructure (RPKI) Origin
  Validation for BGP Export*. R. Bush et al., 2020.
  <https://www.rfc-editor.org/rfc/rfc8893>. ROA-based origin validation.

## Data sources

- **RIPE RIS** — Routing Information Service. Public BGP collectors
  (`rrc00`–`rrcNN`); MRT-formatted updates and RIB dumps over HTTP.
  <https://ris.ripe.net/>.
- **RouteViews** — University of Oregon's collector network, similar shape
  and format to RIS. <https://www.routeviews.org/>.
- **`pybgpstream`** — Python wrapper around CAIDA's libBGPStream MRT
  parser. <https://bgpstream.caida.org/docs/api/pybgpstream/>.
- **RIPE Atlas** — Active measurement probes (ping, traceroute, DNS,
  HTTP) used as the second signal in NetPulse's planned fusion.
  <https://atlas.ripe.net/>.

## Incident primary sources

- **2008 YouTube /24 sub-prefix hijack** — RIPE NCC case study,
  *YouTube Hijacking: A RIPE NCC RIS Case Study*.
  <https://www.ripe.net/publications/news/youtube-hijacking-a-ripe-ncc-ris-case-study/>.
  Used as the source for `data/incidents/youtube_2008.json`.
- **Amazon Route 53 / MyEtherWallet 2018 hijack** — Cloudflare blog,
  *BGP Leaks and Cryptocurrencies* (Tom Strickx, 2018).
  <https://blog.cloudflare.com/bgp-leaks-and-crypto-currencies/>.
  Cited in the `BENCHMARK.md` open-work block; not yet a populated fixture.

## Detection literature

The detectors here are deliberately simple. The papers below build the
canonical taxonomy of the harder cases:

- Ballani, Francis, Zhang, *A Study of Prefix Hijacking and Interception
  in the Internet*, SIGCOMM 2007. The framing of "exact-prefix" vs.
  "sub-prefix" hijacks the project leans on.
- Lad, Massey, Pei, Wu, Zhang, Zhang, *PHAS: A Prefix Hijack Alert System*,
  USENIX Security 2006. Email-based alerting on origin-AS changes; one of
  the earliest real-world detection systems.
- Sermpezis, Kotronis, Dainotti, Dimitropoulos, *A Survey among Network
  Operators on BGP Prefix Hijacking*, SIGCOMM CCR 2018. Operator
  perspective on which detection signals matter.
- Sermpezis et al., *ARTEMIS: Neutralizing BGP Hijacking Within a Minute*,
  IEEE/ACM ToN 2018. The most-cited open-source comparison point;
  combines RPKI, RIR data, and live monitors. <https://github.com/FORTH-ICS-INSPIRE/artemis>.
- Karlin, Forrest, Rexford, *Pretty Good BGP*, IEEE Network 2006. Latency
  vs. accuracy trade-off central to streaming detection.

## Operational reports we draw framing from

- **Cloudflare Radar** routing-incidents view — public dashboards of
  observed hijacks, leaks, and outages. <https://radar.cloudflare.com/>.
- **NIST Internet Time Service** routing-anomaly bulletins.
  <https://www.nist.gov/itl/ssd/routing-information-service>.
- **bgp.tools** — operator-facing live BGP table and historical
  inspection. <https://bgp.tools/>.
