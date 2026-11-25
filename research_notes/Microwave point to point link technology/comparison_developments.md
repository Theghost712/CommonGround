# Point-to-Point Microwave Links: Comparison with Alternatives and Recent Developments (as of 2026)

Research status note: the Ericsson and Dell'Oro websites could not be fetched in this session (DNS resolution failed for www.ericsson.com and www.delloro.com). Figures attributed to them below come from search-result summaries and reprints, not from the primary pages. Those figures should be checked against the originals before publication. Several cost figures come from vendors (Ceragon, Bridgewave) and are marked as such.

## 1. When is microwave cheaper or faster to deploy than fiber, and when is it not?

### Takeaway
Microwave generally wins on cost and speed where fiber must be newly trenched, especially in rural or low-density routes. Fiber wins on capacity headroom and long-term scalability. No authoritative 2025 side-by-side cost-per-site study was found; the cost evidence is largely vendor-authored and route-dependent.

### Cited Findings
- Ericsson's October 2025 Microwave Outlook projects a near-even split of mobile backhaul by 2030: 49% microwave and 51% fiber. Ericsson's framing is that both are needed. Ericsson also says fiber on routes without existing access can cost far more than a microwave link. — [Ericsson news, Oct 2025](https://www.ericsson.com/en/news/2025/10/microwave-outlook-2025-near-fiber-split-ai-and-2x-capacity) (summary via search; primary page not fetched)
- Ericsson's Microwave Outlook 2025 report states microwave backhaul is used in 75% of live 5G networks globally. — [Ericsson Microwave Outlook 2025 report](https://www.ericsson.com/4a8a43/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report.pdf) (summary via search; PDF not fetched)
- Fiber deployment cost benchmark, cited by Ceragon from the 2025 U.S. Fiber Deployment Cost Annual Report: median about USD 18 per foot underground and USD 8 per foot aerial. At those medians, a 5-mile (26,400 ft) route is about USD 211,000 aerial (8 x 26,400) or USD 475,000 underground (18 x 26,400). Ceragon is a microwave vendor, so treat this as an interested-party benchmark. — [Ceragon, "Fiber vs. Wireless"](https://www.ceragon.com/blog/fiber-vs-wireless-the-greatest-debate-of-the-decade)
- Bridgewave claims a point-to-point link can cost only "a few thousand dollars" and that, even where fiber exists, its radio offers about an 80% cost benefit over five years, mainly from lower site-leasing costs. This is an unverified vendor claim. — [Bridgewave, "Navigator pulls out all the stops"](https://bridgewave.com/navigator-pulls-out-all-the-stops/) (surfaced by search; not independently verified)
- Academic TCO work: Lashgari et al. (Chalmers; ECOC 2022 and JOCN 2023) compare fiber and microwave TCO for 5G transport. The authors note device costs depend on transport requirements and that trenching and labor costs vary by country. Headline figures were not retrieved. — [Chalmers research record 535216](https://research.chalmers.se/publication/535216/file/535216_Fulltext.pdf) (not read in full)
- Capacity: Ericsson's 2025 outlook reports a roadmap of roughly 2x mmWave capacity, with work on "ways to double mmWave capacity." — [Ericsson, mmWave capacity report](https://www.ericsson.com/4a8a43/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report_exploring-ways-to-double-mmwave-capacity.pdf) (title and search summary only)
- Ceragon's product page for its E-band universal radio is titled "20 Gbps mmW Universal E.band Radio," indicating roughly 20 Gbps per E-band radio class. — [Ceragon IP-50E](https://www.ceragon.com/products/ip-50e) (product title only; spec sheet not read)

### Inferences
- The cost case for microwave depends mainly on the cost of trenching and of site leasing. Where fiber already reaches the site, the cost comparison shifts toward fiber, and vendor claims about microwave savings are weaker.
- Ericsson's 49/51 split implies that microwave is expected to remain a large share of mobile backhaul through 2030, not a disappearing niche.

### Gaps
- No independent 2025–2026 cost-per-kilometer or cost-per-site comparison was found. The Chalmers TCO headline numbers were not retrieved.
- Ericsson and Dell'Oro primary pages could not be fetched, so the figures above rely on secondary summaries.
- No operator-published cost data for microwave versus fiber was found.

## 2. How do latency and reliability compare with fiber, FSO, and LEO satellite?

### Takeaway
Latency data for terrestrial microwave backhaul was not found, so the comparison with fiber cannot be quantified from these sources. FSO availability is weather-limited, with one 2025 trial showing 92% availability including slow fades and 99% excluding them. LEO satellite (Starlink) median latency in 2025 was roughly 25–50 ms, above typical fiber figures.

### Cited Findings
- Starlink median latency, Ookla Q1 2025 data: 45 ms, compared with 683 ms (HughesNet) and 684 ms (Viasat), both GEO. — Ookla Q1 2025 data as summarized in search; [ComSoc TechBlog on GEO vs LEO](https://techblog.comsoc.org/tag/hughesnet-and-viasat/) (secondary; the Ookla primary URL was not retrieved)
- Starlink's own network update reports median peak-hour latency of 25.7 ms across U.S. customers as of June 2025. — [Starlink network update](https://starlink.com/updates/network-update) (company-reported)
- An IETF measurement study (IRTF open meeting 123) found bent-pipe latency of 35–50 ms globally, with outliers above 100 ms. — [IETF 123 IRTF slides](https://datatracker.ietf.org/meeting/123/materials/slides-123-irtfopen-a-multifaceted-look-at-starlink-performance-00)
- Fiber to nearby destinations: typical total latency is 10–30 ms, and about 2–5 ms to nearby destinations. These figures came from an unlabelled search summary; no reliable primary source was confirmed, so they are not cited as fact here. — (unverified)
- Fiber distance floor: a 2020 analysis is cited in search as stating fiber cannot deliver round-trip latency below 55 ms over the relevant minimum distance. This is dated and unverified. — (unverified)
- FSO availability, 4.6 km urban coherent link, six-day trial including clear sky to thick fog: 92% availability including slow fades and 99% excluding slow fades, at 500 Gb/s. — [arXiv 2507.06051](https://arxiv.org/pdf/2507.06051)
- ITU-R P.1814-1 (revised September 2025) provides prediction methods for FSO attenuation in clear air, fog and rain, and for scintillation. — [ITU-R P.1814-1](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.1814-1-202509-I!!PDF-E.pdf)
- An older Islamabad study found fog has the largest effect on FSO link performance, and that long-term weather evaluation is needed before deployment. — [arXiv 1711.10869](https://arxiv.org/pdf/1711.10869) (older, historical)
- ABI Research recommends pairing FSO with microwave for fallback during adverse weather, and reports Bharti Airtel was reportedly hesitant to commercially deploy Google's Taara FSO over bad-weather availability concerns. The second point is reported, not confirmed. — [ABI Research, FSO](https://www.abiresearch.com/market-research/insight/7784759-with-advancements-in-technical-capabilitie)
- Ericsson's 2025 outlook reports that the W-band achieves 90% of E-band hop lengths and D-band 60%. — [Ericsson Microwave Outlook 2025 report](https://www.ericsson.com/4a8a43/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report.pdf) (summary via search)

### Inferences
- Starlink's median latency (25–50 ms) is comparable to some cable and DSL links but still above typical fiber latency. Fiber is the lowest-latency option on the sources found, but the sources do not give a microwave latency figure to compare.
- FSO's availability gap between "including" and "excluding slow fades" (92% vs 99% in one trial) indicates that prolonged fog, not short fades, drives outages. A hybrid FSO plus microwave design is the common mitigation.

### Gaps
- No latency measurements for terrestrial microwave point-to-point backhaul were found. The microwave-vs-fiber latency comparison is therefore unquantified.
- No FSO latency figure was found.
- No independent microwave availability figure (for example, percent availability per year for a given hop length) was found.
- Starlink-specific backhaul (as opposed to consumer broadband) latency was not separately found.

## 3. What are the most significant recent technical or market developments (2024–2026)?

### Takeaway
The main developments are the shift to E-band and V-band radios with longer hop reach, rising spectrum interest in W-band and D-band (with commercial deployment mostly projected for 2028–2030), AI-based network management now shipping in operator deployments, and a 2026 market outlook that is more positive than the 2025 forecast. Dell'Oro's outlooks conflict on timing.

### Cited Findings

**E-band and V-band radios**
- Ceragon launched the IP-50EXP on June 18, 2025: a high-power E-band radio with 24 dBm extended Tx power, low RSL thresholds and an optional E-stabilizer antenna, intended to achieve link distances comparable to traditional microwave radio. — [Ceragon IP-50EXP announcement](https://www.ceragon.com/news/ceragon-introduces-ip-50exp-delivering-millimeter-wave-capacity-over-microwave-distances)
- Ceragon reported three E-band proof-of-concept deployments with Tier-1 operators and a leading ISP across North America and Europe, with auto-alignment and E-stabilizer innovations. Exact dates were not confirmed. — [Barchart / Ceragon release](https://www.barchart.com/story/news/35603438/ceragon-demonstrates-e-band-innovations-in-tier-1-and-isp-deployments-across-north-america-and-europe)
- Ceragon's IP-100E was one of five planned E-band solutions; Ceragon describes 2025 as "the year of E-band." — [Ceragon IP-100E launch blog](https://www.ceragon.com/blog/ceragon-connects-ip100e-launch) (company framing)
- Ceragon's V-band EH series: EH-614TX provides 1 Gbps aggregated bandwidth on 60 GHz V-band. — [Ceragon search summary](https://www.ceragon.com/products/millimeter-wave-ptp) (not verified against datasheet)
- Ericsson's 2022 report noted that V-band first-generation products have been on the market for a long time but volumes have never taken off. This is historical context. — [Ericsson Microwave report 2022](https://www.ericsson.com/4a81b8/assets/local/reports-papers/microwave-outlook/2022/microwave-report-2022-spectrum-in-a-dynamic-market.pdf) (older)
- Dell'Oro's January 2025 outlook forecasts E/V-band systems in much higher demand because 5G needs more backhaul capacity. Dell'Oro's July 2026 coverage gives an E/V-band shipment forecast of 16% CAGR over the next five years. — [Dell'Oro, 5G mobile backhaul forecast](https://www.delloro.com/?p=1974) and [Dell'Oro news via Microwave Journal](https://www.microwavejournal.com/articles/45406-microwave-transmission-equipment-market-flattens-out-in-2025) (summaries; July 2026 coverage not read directly)

**W-band and D-band (sub-THz) backhaul**
- Nokia completed a full-duplex D-band (130–175 GHz) wireless transport trial, then added dual polarization, projecting 25 Gbps per direction on a single 2 GHz channel (about 50 Gbps on a 2+2 GHz FDD license). Nokia expects first commercial D-band deployments between 2028 and 2030. — [Nokia blog, D-band dual-polar capacity](https://www.nokia.com/blog/innovation-for-d-band-microwave-transport-dual-polar-capacity-boost/) (vendor projection)
- A W-band trial (Ericsson, Deutsche Telekom and Cosmote, per ABI Research) reported 5.7 Gbps over 1.5 km and more than 10 Gbps over 1 km hops. Trial date not confirmed. — [ABI Research, W-band backhaul](https://abiresearch.com/market-research/product/7779446-5g-backhaul-dipping-toes-in-w-band-frequen) (date unknown)
- ABI long-term target: up to 100 Gbps (4x25 Gbps MIMO) in 5 GHz channels in W- and D-band. W-band (92–114 GHz) has about 15 GHz of spectrum and D-band (130–175 GHz) about 30 GHz, per ABI. — same ABI source
- Fraunhofer IAF/HHI and LG (December 2024): a D-band 160 GHz hybrid beamforming trial, which is a mobile-access test rather than backhaul. — [Fraunhofer press release](https://iaf.fraunhofer.de/en/media-library/press-releases/d-band-demo-6g.html)
- NTT and Keysight: a sub-THz power-amplifier component test reached 280 Gbps in June 2025. This is a component result, not a link. — (search summary only; not linked to a primary page)

**Ericsson market outlook and satellite interference**
- Ericsson's October 2025 Microwave Outlook: W-band and D-band hop lengths noted above. — [Ericsson news](https://www.ericsson.com/en/news/2025/10/microwave-outlook-2025-near-fiber-split-ai-and-2x-capacity)
- Ericsson's 2026 Microwave Outlook discusses satellite interference with fixed-service E-band links and describes it as manageable. — [Ericsson Microwave Outlook 2026](https://www.ericsson.com/4a9c7f/assets/local/reports-papers/microwave-outlook/2026/microwave-outlook-report-2026.pdf) (summary via search; not read in full)
- Ericsson 2026 blog title "Microwave is the new fiber: rethinking 5G backhaul." — [Ericsson blog 2026](https://www.ericsson.com/en/blog/middle-east-africa/2026/microwave-is-the-new-fiber-rethinking-5g-backhaul) (not fetched)

**Market (Dell'Oro and vendors)**
- Dell'Oro: global point-to-point microwave transmission equipment revenue fell 1% in 2025, after growth in the first half. The second half was weak, with slower demand in India and Latin America. Mobile backhaul shipments still rose during 2025. — [Dell'Oro, Feb 2026 release, via search](https://www.delloro.com/?p=6492) (summary; primary page not fetched)
- Dell'Oro: top-six vendor share rose from 85% (2024) to 87% (2025). — same source
- Dell'Oro forecasts conflict on timing: the February 2026 release says at least two more years of growth (through about 2027), the July 2026 coverage says fiber-based mobile backhaul will overtake wireless share during the forecast period with a peak around 2028, and the January 2025 five-year outlook projected contraction starting in 2028. — [Dell'Oro, Microwave Transmission](https://www.delloro.com/?p=6492); [Dell'Oro, 5G mobile backhaul forecast](https://www.delloro.com/?p=1974)
- Dell'Oro's 5G mobile backhaul transport forecast: 12% CAGR from 2024 through 2028. — [Dell'Oro, 5G mobile backhaul forecast](https://www.delloro.com/?p=1974)
- Ceragon: Q1 2026 revenue USD 85.0 million (down 4.1% from USD 88.7 million in Q1 2025); Q2 2026 growth of 14% year over year, driven by India; Q3 2026 (reported November 5, 2026) narrowed full-year 2026 revenue guidance to USD 365–375 million and non-GAAP gross margin to 33.5–34.5%, citing growing E-band interest. — [Ceragon Q2 2026](https://www.morningstar.com/news/pr-newswire/20260811io22600/ceragon-reports-2026-second-quarter-financial-results), [Ceragon Q3 2026](https://finviz.com/news/416707/ceragon-reports-2026-third-quarter-financial-results), [Ceragon Q1 2026](https://www.barchart.com/story/news/2010926/ceragon-networks-reports-2026-first-quarter-financial-results)
- Aviat Networks: the latest found was fiscal Q2 2026 (February 3, 2026), with full-year revenue guidance of USD 440–460 million and adjusted EBITDA USD 45–55 million. Later guidance was not found. — [Aviat fiscal Q2 2026](https://www.barchart.com/story/news/3407/aviat-networks-announces-fiscal-2026-second-quarter-and-six-month-financial-results)

**AI-driven and software-defined link management**
- O2 Telefónica Germany (described in Ericsson's October 2025 Microwave Outlook) is exploring AI in microwave network management. The report cites a case where timely action kept a site from becoming a "Red Site," and says AI can detect slight antenna misalignments from storms and locate developing cable faults. — [Ericsson Microwave Outlook 2025 report, AI-based backhaul management](https://www.ericsson.com/4a8a42/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report_ai-based-backhaul-management.pdf) (vendor-reported operator case; not independently verified)
- The same report gives an example of an outage traced to a construction crane blocking a link during working hours. — same source
- Ericsson Transport Automation Controller uses AI/ML to analyze microwave, IP and optical networks with root-cause views. The concept dates to a 2020 RCR Wireless piece, so it is not new in 2025. — [RCR Wireless, 2020](https://www.rcrwireless.com/20201006/5g/ai-and-machine-learning-simplify-microwave-network-management) (historical)
- A Columbia University patent describes predictive weather-based management that uses a network's own commercial microwave links to forecast attenuation and drive adaptive modulation, power control and rerouting. This is a technology description, not a confirmed deployment. — [Columbia Technology Ventures](https://inventions.techventures.columbia.edu/technologies/predictive-network--CU19208)
- ITU AI for Good 2025 covers reinforcement learning for adaptive modulation on FSO links (not microwave). — [ITU AI for Good 2025](https://www.itu.int/net/epub/TSB/2025-AI-for-Good-Innovate-for-Impact/files/basic-html/page389.html)

**Microwave in 5G and open RAN backhaul**
- Ericsson projects microwave and fiber near even for mobile backhaul by 2030 (49/51). — see Section 1
- Open RAN deployments (AT&T): the first open RAN call with third-party radios on a commercial network (Ericsson basebands, 1Finity radios) was announced in August 2025, and a third-party rApp went live in production. AT&T's Ericsson open RAN contract is described as multi-year, USD 14 billion, aiming for 70% of wireless traffic on open platforms by late 2026. — [RCR Wireless, AT&T open RAN, Aug 2025](https://rcrwireless.com/20250805/carriers/att-ericsson-open-ran); [AT&T blog, Oct 2025](https://about.att.com/blogs/2025/pushing-forward-on-open-ran.html)
- Rakuten Mobile with 1Finity targets 3,000 open RAN sites by end of 2027 (original target end of 2026). — [Light Reading, 1Finity at Rakuten](https://www.lightreading.com/open-ran/1finity-ramps-open-ran-at-rakuten-mobile-and-beyond)
- Analysys Mason's 2025 Open Network Index (survey of 50 Tier 1 operators) reports open-network progress. Its details were not retrieved. — [Analysys Mason report](https://www.analysysmason.com/research/content/perspectives/open-network-index-rma16-rma18/report-pdf)

### Inferences
- E-band and V-band are the near-term capacity expansion path for microwave. W- and D-band are being prepared, but the sources put commercial D-band deployment at 2028–2030, so they are not a 2026 option.
- Vendor and analyst outlooks disagree on whether the market is at a peak. The 2026 outlook is more positive than the January 2025 forecast, but the timing of contraction is inconsistent across sources.
- AI-driven management is moving from concept to early operator trials, but independent evidence of measured benefit is thin.

### Gaps
- No open RAN deployment using microwave backhaul as the transport layer was found. The open RAN and microwave threads were covered separately.
- The E-band satellite-interference point is from Ericsson's 2026 report summary only.
- The Ceragon E-band deployments were not dated.
- No peer-reviewed field trial of AI-driven microwave link management was found.
- The Dell'Oro July 2026 report and the full Ericsson 2026 outlook were not read.

## 4. What are the main limitations and risks (weather, tower capacity, spectrum scarcity)?

### Takeaway
Weather (rain fade, fog, turbulence) is the dominant technical limit for microwave at high frequencies and for FSO. Spectrum scarcity is pushing operators toward E-band, V-band and later W/D-band, which have shorter hop lengths. Tower and site capacity are cited as constraints, but no quantified source was found. Satellite interference with E-band fixed links is a newer risk flagged in Ericsson's 2026 outlook.

### Cited Findings
- Weather: fog has the largest effect on FSO link performance; atmospheric turbulence is the key degradation source for FSO reliability. — [arXiv 1711.10869](https://arxiv.org/pdf/1711.10869); [arXiv 2012.00155 survey](https://arxiv.org/pdf/2012.00155) (older)
- Hop length: W-band achieves 90% of E-band hop lengths and D-band 60%, per Ericsson's 2025 outlook. — [Ericsson Microwave Outlook 2025 report](https://www.ericsson.com/4a8a43/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report.pdf) (summary)
- Adaptive modulation: during fades, microwave links step down modulation to keep the link up, which lowers capacity. Operators must define service levels to benefit from this. — [Microwave Journal, adaptive modulation](https://www.microwavejournal.com/articles/12354-network-engineering-with-adaptive-modulation)
- Spectrum: W-band has about 15 GHz and D-band about 30 GHz, per ABI. — [ABI Research, W-band](https://abiresearch.com/market-research/product/7779446-5g-backhaul-dipping-toes-in-w-band-frequen)
- Satellite interference: Ericsson's 2026 outlook discusses satellite interference with fixed-service E-band links and calls it manageable. — [Ericsson Microwave Outlook 2026](https://www.ericsson.com/4a9c7f/assets/local/reports-papers/microwave-outlook/2026/microwave-outlook-report-2026.pdf) (summary)
- Vendor concentration: top six microwave vendors hold 87% of revenue in 2025, up from 85% in 2024. — [Dell'Oro, via Microwave Journal](https://www.microwavejournal.com/articles/45406-microwave-transmission-equipment-market-flattens-out-in-2025)
- Weather-related outage and availability: the 4.6 km FSO trial showed a 7-point gap (92% vs 99%) between availability including and excluding slow fades. — [arXiv 2507.06051](https://arxiv.org/pdf/2507.06051)
- Physical obstructions: an outage traced to a construction crane blocking a link. — [Ericsson Microwave Outlook 2025, AI report](https://www.ericsson.com/4a8a42/assets/local/reports-papers/microwave-outlook/2025/microwave-outlook-2025_report_ai-based-backhaul-management.pdf)

### Inferences
- Shorter hop lengths at E-band and above mean more sites per route, which increases tower and site demands. This is an inference from the hop-length figures, not a sourced claim.
- Spectrum scarcity favors higher bands, but higher bands are more weather-sensitive. Operators therefore face a trade-off between capacity and availability.

### Gaps
- No quantified source on tower capacity, structural loading or site-lease constraints was found.
- No measured rain-fade availability figure for E-band or V-band hops (for example, percent availability at a specific hop length and rain rate) was retrieved. ITU-R rain-attenuation methods were not checked.
- Regulatory spectrum-allocation timelines (for example, national E-band or W-band licensing decisions) were not researched.

## Source access note
- www.ericsson.com and www.delloro.com could not be fetched in this session because the hosts did not resolve. Those sites need to be allowed in the session's network settings before the primary reports can be read and checked.
