# Microwave Point-to-Point Link Technology: Fundamentals

**Research status:** Partial. Only the search tool worked. Every direct fetch of an ITU, Ericsson, Analog Devices or Cambium page failed because those hosts do not resolve from this session (www.itu.int, www.ericsson.com, www.analog.com, community.cambiumnetworks.com). Most figures below therefore come from search-result snippets, not from the full documents. Each bullet notes whether the figure was confirmed by a fetch or taken from a snippet only. Verify before relying on any number in a design or published report.

**Currency:** Figures are dated 2019 to 2026 where the source gives a date. Older figures are marked as historical.

---

## Key Question 1: Which frequency band suits a given hop length versus capacity, and why?

### Takeaway
Lower bands (roughly below 11 GHz) give long hops (tens of km) at modest capacity. Bands from about 11 to 23 GHz give medium hops (a few to ~15 km) at higher capacity. E-band (71-86 GHz) gives multi-Gbps capacity but hops of roughly 1-7 km, and rain fade sets the limit. Band choice is a trade between free-space path loss, rain attenuation, available bandwidth and licensing.

### Cited Findings
- ITU-R F.2086 (2015) qualitatively groups the bands: lower microwave bands below about 11 GHz allow long hops, medium bands about 11-23 GHz allow relatively long hops, and bands above about 23 GHz suit short links. Source: [ITU-R F.2086](https://www.itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.2086-0-201509-I%21%21PDF-E.pdf). *Snippet only; no km figures in the snippet.*
- ITU-R F.1102 states that above about 17 GHz, hop length is limited by rain attenuation, and that precipitation outage critically determines hop length. Source: [ITU-R F.1102](https://itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.1102-1-200202-S!!PDF-E.pdf). *Snippet only.*
- Wikipedia's microwave-link article gives typical terrestrial backbone hops of about 10 to 60 km, with a record hop of 360 km at 2 GHz. Source: [Wikipedia, Microwave link](https://en.Wikipedia.com/wiki/Microwave_link). *Secondary source; snippet only.*
- Ericsson (2019) reports that E-band hops were often assumed to be limited to 1-2 km, and that dropping the "five nines" availability target allows longer E-band hops. Its examples include a 7 km E-band hop in rain zone E, and in Poland 11% of E-band hops exceed 6 km. Source: [Ericsson, Lessons learned from a decade with E-band (2019)](https://www.ericsson.com/4aef65/assets/local/reports-papers/microwave-outlook/2019/lessons-learned-from-a-decade-with-e-band-article-co-screen.pdf). *Snippet only.*
- CommScope's dual-band modelling paper gives maximum path lengths for a BPSK link at 186 Mbps and 99.999% rain availability: 2.44 km at 80 GHz and 11.31 km at 23 GHz. These are modelling outputs, not datasheet specifications. Source: [CommScope, dual-band white paper](https://COMMSCOPE.COM/globalassets/digizuite/602438-dual-band-wp-114222-en.pdf). *Snippet only.*
- An ACMA (Australia) band-utilisation table lists minimum path lengths per band; the snippet shows 40 km for the 3.8 GHz long-haul band. The 6, 11, 18, 23 and 38 GHz rows were not visible. Source: [ACMA, RF channel arrangements appendix](https://acma.gov.au/sites/default/files/2023-06/Appendix%201%20preamble%20RF%20Channel%20Arrangements%20and%20Assignment%20Instructions.pdf). *Snippet only.*
- A Scribd copy of a "typical hop length by band" table (attributed to ITU-R Radio Regulations) was garbled in extraction. Its readable fragments suggest about 2 km maximum for the 18 and 23 GHz rows. Not usable without checking the original. Source: [Scribd, Freq band and max length](https://www.scribd.com/document/489158569/Freq-Band-and-Max-length). *Unverified.*

### Inferences
- Free-space loss rises with frequency, and rain loss rises much faster. Above about 10-17 GHz, rain fade rather than distance limits hop length (follows from the F.1102 statement).
- Because E-band offers about 10 GHz of total spectrum (see Key Question 4), it is chosen for capacity over short hops, not for reach.
- Relaxing availability from 99.999% to 99.99% is a major lever for longer E-band hops (follows from the Ericsson 2019 statement).

### Gaps
- No verified, band-by-band table of typical hop lengths for 6, 7/8, 11, 13, 15, 18, 23, 26 and 38 GHz. The ITU-R source for this was not reachable. Needed: ITU-R F.1609 or F.2086 full text, or a vendor planning guide.
- No verified figures for 13, 15, 26 and 60 GHz hop lengths.

---

## Key Question 2: How much does rain fade limit range at each band, and how is it mitigated?

### Takeaway
At 70-80 GHz, rain attenuation is roughly 10 dB/km at 25 mm/h and about 30 dB/km at 100 mm/h, which limits practical links to a few km. Lower bands lose far less per km. Mitigation is through shorter hops, higher link margin, lower modulation during fades (adaptive modulation), dual-band pairing and stricter or looser availability targets.

### Cited Findings
- CommScope states that at 80 GHz, rain attenuation is about 10 dB/km at 25 mm/h and about 30 dB/km at 100 mm/h. Source: [CommScope blog, Optical fiber in the air](https://www.commscope.com/Blog/Optical-Fiber-in-the-Air). *Figure came from a search summary; the page was not fetched, so confirm the exact text.*
- A search-summary source states that practical 70/80 GHz links are much shorter than the clear-air range because of rain (up to about 30 dB/km at rain rates below 100 mm/h). It also states that current 70/80 GHz equipment can reach 1 Gbps at 99.999% weather availability. Source: [Cablefree, E-band MMW technology](https://cablefree.net/wirelesstechnology/millimeter-wave-technology/e-band-mmw-technology/). *Snippet only; the author of the 1 Gbps claim is not identified.*
- CommScope's dual-band 23/80 GHz and 18/80 GHz antenna work reports that pairing a lower band with 80 GHz extends link length and reduces link degradation. Source: [CommScope dual-band white paper](https://COMMSCOPE.COM/globalassets/digizuite/602438-dual-band-wp-114222-en.pdf). *Snippet only.*
- Ericsson's 2019 report: its E-band rain-zone examples and 7 km hop show that rain zone (ITU-R P.837 zone) sets the achievable distance at a given availability. Source: [Ericsson 2019](https://www.ericsson.com/4aef65/assets/local/reports-papers/microwave-outlook/2019/lessons-learned-from-a-decade-with-e-band-article-co-screen.pdf). *Snippet only.*
- ITU-R P.530 is the prediction method for rain and multipath effects on digital fixed line-of-sight links. It takes specific attenuation from ITU-R P.676 and includes gaseous absorption above about 10 GHz. Current edition is P.530-19 (September 2025). Source: [ITU-R P.530-19 summary](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.530-19-202509-I!!SUM-HTM-E.htm). *Snippet only; equations not read.*

### Inferences
- The gap between 25 mm/h and 100 mm/h rain rates (about 3x attenuation at 80 GHz) explains why rain-zone choice matters more than frequency alone for E-band.
- Lower bands (for example 6-11 GHz) are rain-limited much less; their limits are mainly path loss and interference.

### Gaps
- No verified rain-attenuation figures (dB/km at 25, 50 and 100 mm/h) for 6, 11, 18, 23 and 38 GHz. These need the ITU-R P.838 specific-attenuation coefficients, which were not retrieved.
- The mitigation list is from general knowledge and dual-band snippets. Specifically, the effect of ACM on availability, and a quantified fade margin per band, are not sourced here.
- One unidentified source states 99.999% availability needs coping with 100 mm/h rain in ITU rain zone K (New York City). It is secondary and unverified; check against ITU-R P.837 rain statistics.

---

## Key Question 3: What line-of-sight clearance and Fresnel zone rules apply?

### Takeaway
The common planning rule is at least 60% of the first Fresnel zone radius clear of obstructions, with about 80% preferred. Some vendor guidance allows up to 40% obstruction and recommends about 20% or less. ITU-R P.530 gives the formal basis for the 60% rule and adds effective-earth-radius and diffraction methods above about 2 GHz.

### Cited Findings
- ITU-R P.530 (the recommendation on line-of-sight design) states that the direct path needs clearance of at least 60% of the first Fresnel zone radius to achieve free-space propagation conditions. Above about 2 GHz, diffraction fading is handled by raising antennas, using effective-Earth-radius factors and separate temperate and tropical clearance rules. Source: [ITU-R P.530-18](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.530-18-202109-I!!PDF-E.pdf). *Stated in a search summary; the PDF was not read, so confirm the exact clause.*
- Wikipedia gives the rule of thumb as ideally 80% clear and at least 60% clear. Source: [Wikipedia, Fresnel zone](https://en.wikipedia.org/wiki/Fresnel_zone). *Secondary.*
- Cambium's community guidance uses the 60% rule, states a maximum allowable obstruction of 40%, and recommends 20% or less. Source: [Cambium Networks community, Fresnel zone recommendations](https://community.cambiumnetworks.com/t/fresnel-zone-recommendations/54685). *Snippet only; the page was not fetched.*
- A calculator (L-com) gives first-zone radius r1 = 17.3 × sqrt(d1·d2 / (f·D)) metres, with d1 and d2 in km, D = d1 + d2 in km, and f in GHz. Obstacle-free radius = 0.6 × r1. Source: [L-com, Fresnel zone clearance calculator](https://www.l-com.com/resources/wireless-calculators/fresnel-zone-clearance-calculator). *Formula stated in a search summary; the 17.3 constant is the standard value for metres/km/GHz.*
- A YDI Wireless article states that a partly blocked Fresnel zone can still work if the link budget has enough margin, and that the 60% requirement matters more as distance grows. *No URL captured for this article; treat as unsourced.*

### Inferences
- The first-zone radius scales with the square root of path length and inversely with frequency: at 80 GHz the first zone is roughly 3.6 times narrower than at 6 GHz for the same path. This is why high-band links are less sensitive to clearance at a given distance, but need tighter pointing and alignment.
- The 60% rule is a planning criterion, not a hard limit. Margin is the other lever.

### Gaps
- Not verified: the exact P.530 clause and any frequency-dependent exceptions.
- No verified guidance on minimum tower height or antenna-height rules by band.
- No verified guidance on earth-bulge (k-factor) values; P.453 and P.310 were named by search results but not read.

---

## Key Question 4: What capacities and modulation schemes are typical in current equipment?

### Takeaway
Current E-band equipment supports channel bandwidths of about 62.5 MHz to 2 GHz and aggregate rates up to 10 Gbps, with modulation from BPSK to 1024QAM (Huawei RTN 380AX). Lower-band (6-38 GHz) radios typically support 256QAM to 4096QAM with ACM. Vendor modulation ceilings vary by product and model, and the sources below are mixed in date. Treat them as indicative.

### Cited Findings
- E-band spans two 5 GHz blocks, 71-76 GHz and 81-86 GHz (10 GHz total), divided into channels of 250 MHz in common plans. Sources: [Analog Devices, E-band wireless radio links](https://www.analog.com/en/resources/technical-articles/e-band-wireless-radio-links.html) and [Wikipedia, E band (waveguide)](https://Www.Wikipedia.org/wiki/E_band_(waveguide)). *Snippet only for Analog Devices.*
- Huawei RTN 380AX (E-band) lists channel bandwidths of 62.5 MHz to 2000 MHz, maximum throughput of 10 Gbps, and modulation BPSK to 1024QAM. Source: [Huawei, E-band millimeter radio](https://e.huawei.com/ph/products/wireless/microwave/e-band-millimeter). *Snippet only; no 2500 MHz channel found in any source.*
- A Huawei result describes 64QAM over two 250 MHz channels at up to 2.5 Gbps. Source: same Huawei page family. *Snippet only; date unclear.*
- Ericsson's long-haul material shows the availability trade-off: 1024QAM at 99.99% versus 128QAM at 99.999% for the same link. Source: [Ericsson, Microwave report 2020: long-haul use](https://www.ericsson.com/4a8f9a/assets/local/reports-papers/microwave-outlook/2020/microwave-report-2020-long-haul-use.pdf). *Snippet only; the exact table was not read.*
- Ceragon IP-20V (V-band, 60 GHz) datasheet, Rev D (dated May 2023 in the search summary): modulation BPSK to 128QAM, with ACM. Source: [Ceragon IP-20V datasheet (Scribd copy)](https://www.scribd.com/document/683256224/Ceragon-IP-20V-V-Band-Datasheet-Rev-D). *Third-party copy; confirm against Ceragon.*
- Aviat iPASOLINK EX Advanced datasheet (2024, per search summary): QPSK, 8PSK, 16, 32, 64, 128 and 256QAM with AMBR for 71-86 GHz. Aviat iX Advanced material is reported to support up to 4096QAM. *No URL verified; both claims are from snippets.*
- Aviat CTR 8540 datasheet (2011, historical): QPSK, 16, 64 and 256QAM with ACM. *Historical; snippet only.*
- Ceragon IP-20 2025 training material describes ACM and MSE but gives no modulation ceiling. A RAD page (older) gives up to 2.5 Gbps over a 500 MHz channel. *Historical; snippet only.*

### Inferences
- Capacity per link rises with channel bandwidth times spectral efficiency (bits/s/Hz). Higher-order QAM (256 to 1024QAM) needs more link margin, so higher-order modes are typically reached only in short or clear-air hops. ACM steps the modulation down during fades, trading capacity for availability.
- Current E-band products achieve multi-Gbps at short hops, while the 1 Gbps at 99.999% figure suggests the practical rate in rain-prone areas is much lower than the peak.

### Gaps
- No verified current (2025-2026) modulation ceiling for Ceragon IP-20 or Ericsson MINI-LINK / Nokia products.
- No verified channel bandwidths or capacities for 6-38 GHz bands (for example 56 MHz at 6 GHz, 112 MHz at 11 GHz). These need vendor datasheets.
- No verified antenna sizes or gain figures. Typical gains (for example about 38 dBi for 0.6 m at 23 GHz, 45 dBi-plus for 0.3 m at 80 GHz) were not checked and are not included.
- No verified E-band oxygen/clear-air attenuation source. The search results gave ~0.5 dB/km for E-band and a 15 dB/km peak at 60 GHz, but the sources were not confirmed.

---

## Availability and reliability targets

### Cited Findings
- ITU-R F.1703 sets availability objectives for real digital fixed wireless links, using a 27,500 km hypothetical reference path. Objectives are defined per reference connection, not per hop, so per-hop targets must be derived. Source: [ITU-R F.1703-0](https://www.itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.1703-0-200501-I!!PDF-E.pdf). *Snippet only; objective values not read.*
- Ericsson describes the committed-rate tier as associated with high availability of 99.99% to 99.999%. Source: [Ericsson, Microwave report 2020](https://www.ericsson.com/4a8f9a/assets/local/reports-papers/microwave-outlook/2020/microwave-report-2020-long-haul-use.pdf). *Snippet only.*
- 99.999% availability corresponds to less than 5.3 minutes of outage per year (calculated: 0.001% of 525,600 min). This is arithmetic, not a sourced figure.

### Gaps
- The F.1703 allocation for national-link and per-hop objectives was not read.

---

## Summary of confidence
- **Higher confidence (direct statement in a search summary of an ITU or major vendor source):** Fresnel 60% rule; F.1102 rain-limit statement; E-band 10 GHz spectrum; Huawei 10 Gbps / BPSK to 1024QAM; Ericsson 2019 hop-length observations.
- **Lower confidence (secondary, unidentified, or historical):** rain dB/km figures; 1 Gbps at 99.999%; Aviat 4096QAM; ACMA minimum path length; Scribd hop-length table; the 100 mm/h rain-zone K example.
- **Not established by this research:** per-band hop-length table; rain attenuation for bands below 70 GHz; antenna gain and size; current IP-20 modulation; channel plans for 6-38 GHz.

## Sources reached (search snippets; direct fetch failed for ITU, Ericsson, Analog Devices and Cambium)
- https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.530-18-202109-I!!PDF-E.pdf
- https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.530-19-202509-I!!SUM-HTM-E.htm
- https://itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.1102-1-200202-S!!PDF-E.pdf
- https://www.itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.2086-0-201509-I%21%21PDF-E.pdf
- https://www.itu.int/dms_pubrec/itu-r/rec/f/R-REC-F.1703-0-200501-I!!PDF-E.pdf
- https://www.ericsson.com/4aef65/assets/local/reports-papers/microwave-outlook/2019/lessons-learned-from-a-decade-with-e-band-article-co-screen.pdf
- https://www.ericsson.com/4a8f9a/assets/local/reports-papers/microwave-outlook/2020/microwave-report-2020-long-haul-use.pdf
- https://www.analog.com/en/resources/technical-articles/e-band-wireless-radio-links.html
- https://COMMSCOPE.COM/globalassets/digizuite/602438-dual-band-wp-114222-en.pdf
- https://www.commscope.com/Blog/Optical-Fiber-in-the-Air
- https://cablefree.net/wirelesstechnology/millimeter-wave-technology/e-band-mmw-technology/
- https://e.huawei.com/ph/products/wireless/microwave/e-band-millimeter
- https://community.cambiumnetworks.com/t/fresnel-zone-recommendations/54685
- https://en.wikipedia.org/wiki/Fresnel_zone
- https://www.l-com.com/resources/wireless-calculators/fresnel-zone-clearance-calculator
- https://en.Wikipedia.com/wiki/Microwave_link
- https://Www.Wikipedia.org/wiki/E_band_(waveguide)
- https://acma.gov.au/sites/default/files/2023-06/Appendix%201%20preamble%20RF%20Channel%20Arrangements%20and%20Assignment%20Instructions.pdf
- https://www.scribd.com/document/683256224/Ceragon-IP-20V-V-Band-Datasheet-Rev-D
- https://www.scribd.com/document/489158569/Freq-Band-and-Max-length
