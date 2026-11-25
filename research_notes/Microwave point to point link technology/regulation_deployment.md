# Point-to-Point Microwave Links: Regulation, Licensing, and Deployment Economics

Research date: 2026-11-25. Scope: current rules and market data as of 2026, with older figures labelled as historical.

**Access caveat:** In this session the fetch tool could not resolve www.ofcom.org.uk, www.fcc.gov or www.ericsson.com (DNS failure outside the session's allowed network domains). Regulator and Ericsson findings below come from search-result summaries and the URLs they returned, not from full primary-page reads. Each such item should be re-checked against the primary document before it is quoted in a report. Items that could not be sourced are listed under Gaps.

---

## Key Question 1: How do licensed, light-licensed and unlicensed regimes differ?

### Takeaway
Regimes differ mainly in who coordinates interference and how the licence is granted. Fully licensed Part 101 / Ofcom fixed-link bands use case-by-case licences and coordination before filing. Light-licensed or registration-based regimes (Ofcom's 73/83 GHz self-coordinated bands; the US 70/80/90 GHz link registration model) shift coordination to the operator and a database. US and EU rules for E-band and the upper microwave bands were being actively revised in 2025, so the 2026 position should be checked against the latest FCC and CEPT outputs.

### Cited Findings
- The FCC consolidated private and common-carrier fixed microwave rules into 47 CFR Part 101 in 1996, reorganising parts 21 and 94. Subpart B covers applications and licences (§§101.4–101.97) and Subpart C covers technical standards (§§101.101–101.151). — [Federal Register, 28 May 1996](https://www.govinfo.gov/content/pkg/FR-1996-05-28/html/96-12942.htm) (historical; structure as summarised in search results)
- Under Part 101, applicants generally must coordinate proposed frequency use with existing users in the area before filing; the FCC does not license or endorse frequency coordinators. Minor modifications do not require coordination evidence with the filing, though some may still need coordination. — [47 CFR 101.103](https://www.law.cornell.edu/cfr/text/47/101.103) (text as surfaced in search summary; not fetched in full)
- Applications are filed electronically through the FCC Universal Licensing System (ULS). — Search summary citing [FCC Part 101 microwave page](https://www.fcc.gov/wireless/bureau-divisions/broadband-division/microwave) (page not fetched)
- FCC 2025 proceedings: (a) Lower 37 GHz Report and Order, Sixth Report and Order and Further Notice (WT Docket 24-243, FCC 25-24, April 2025), which asks whether to tighten emissions limits above 37 GHz and whether the initial coordination mechanism can be enhanced, under 47 CFR Part 30; (b) Upper Microwave NPRM (SB Docket 25-305, FCC 25-70, adopted 28 October 2025), under Part 25, which proposes replacing 47 CFR 25.136 with new sharing paradigms. — [FCC 25-70 PDF](https://docs.fcc.gov/public/attachments/FCC-25-70A1.pdf); [Federal Register 2025-21805, "Facilitating More Intensive Use of Upper Microwave Spectrum"](https://www.federalregister.gov/documents/2025/12/03/2025-21805/facilitating-more-intensive-use-of-upper-microwave-spectrum) (listed in search results; content not fetched)
- One search summary reports that the FCC's NPRM is evaluating a light-licensing framework that could replace Part 101's manual coordination with automated registration. — Search summary on [FCC 25-70](https://docs.fcc.gov/public/attachments/FCC-25-70A1.pdf); not confirmed in full text.
- US E-band (70/80/90 GHz) is licensed rather than unlicensed: a non-exclusive nationwide licence combined with registration of each link in the Link Registration System run by third-party database managers; a link may not operate until registered. — Search summary only; no primary text fetched. Source to verify: FCC Part 101 E-band rules (cited as [FR 2024-05390](https://www.govinfo.gov/content/pkg/FR-2024-04-29/html/2024-05390.htm) and [FR 2025-02962](https://www.govinfo.gov/content/pkg/FR-2025-03-06/html/2025-02962.htm) in results; neither was fetched).
- The FCC's October 2025 NPRM comments (reported by Broadband Breakfast) propose a unified system for Q/V-band (37–52 GHz), E-band (70/80 GHz) and W-band (90/100/110 GHz); one commenter urged unlicensed or very-low-power sharing in UMFUS bands. — [Broadband Breakfast](https://broadbandbreakfast.com/fcc-plans-to-overhaul-rules-governing-upper-microwave-spectrum.md) (secondary report; outcome not confirmed)
- Ofcom (UK): 73.375–75.875 GHz and 83.375–85.875 GHz are available under a light-licensed process for point-to-point fixed wireless, described as self-coordinated bands. — [Ofcom, Fixed terrestrial links](https://www.ofcom.org.uk/spectrum/radio-equipment/fixed-terrestrial-links) (via search summary; page not fetched)
- Ofcom (UK): 10, 28, 32 and 40 GHz are block-assigned bands that are also used for fixed links. — [Ofcom, Fixed terrestrial links](https://www.ofcom.org.uk/spectrum/radio-equipment/fixed-terrestrial-links); [Ofcom, 10/28/32 GHz annual licence fees statement](https://www.ofcom.org.uk/spectrum/radio-equipment/annual-licence-fees-10-28-and-32-ghz-spectrum)
- ECC/CEPT: the amended Recommendation on point-to-point fixed wireless channel arrangements in 40.5–43.5 GHz has its latest edition dated 24 January 2025 (first approved 2001; amended 2010 and 2014). ECC Decision (22)05 withdrew ERC Decision (99)15 (approved November 2022). ECC Report 173 (2023) gives an overview of Fixed Service use in Europe. — [CEPT document repository, doc 4608](https://docdb.cept.org/download/4608); [CEPT Fixed Service Recommendations index](https://efis.cept.org/views2/fixedservicerecommendations.jsp) (search summaries; contents not read)
- ECC/REC(05)07 covers 71–76/81–86 GHz channel arrangements and cites ECC/REC(01)05 as the planning reference for digital P-P links. — [CEPT docdb, doc 1853 (Revised ECC/REC/(05)07)](https://docdb.cept.org/download/1853) (search summary)
- Historical: an ETSI white paper (September 2020) surveys worldwide E-band regulation status. — [ETSI WP 37](https://www.etsi.org/images/files/ETSIWhitePapers/etsi-WP-37-E-Band-survey-on-Status-of-Worldwide-Regulation.pdf)

### Inferences
- In the US, the "unlicensed E-band" premise does not hold in the search evidence: E-band is registration-based under a nationwide licence. Unlicensed millimetre-wave use in the US is more likely to refer to 60 GHz (V-band) under FCC Part 15, but no source on that was retrieved in this session, so treat it as unverified.
- The 2025 FCC and CEPT activity points to a shift from case-by-case manual coordination toward database and registration models for the upper microwave and E-band ranges. This is an inference from the NPRM language, not a confirmed rule.
- Ofcom's approach is a hybrid: block-assigned and licensed bands at 10–40 GHz, with light-licensed self-coordinated bands at 73/83 GHz.

### Gaps
- Ofcom light-licensing fee amounts and licence terms were not retrieved (Ofcom fixed-link fee pages were not accessible).
- Whether the FCC adopted any light-licensing or E-band change by late 2026 is not confirmed. The docket status should be checked directly.
- Part 15 V-band (60 GHz) rules were not sourced in this session.
- No source was found for an African or Asian national regulator's microwave licensing regime (e.g. ICASA, TRAI/DoT, NCC) in this session.

---

## Key Question 2: What do licences and installations cost, and how long does coordination take?

### Takeaway
No current (2025–2026) sourced figure was found for all-in per-link cost or per-link licence fees. The only verified cost data are older (2014–2019) or vendor/ambiguous: roughly US$45,000–55,000 per tower for a microwave antenna device line in an NTIA sheet (date unknown; excludes tower and foundation), about US$400/month plus US$100 per linear foot of antenna for tower space (2014, historical), and a 2014 US analyst estimate of about US$1,600/month for a two-antenna link. Coordination timelines were not sourced.

### Cited Findings
- NTIA cost sheet: about US$45,000–55,000 per tower for a microwave antenna device (receives and transmits wireless data). Ranges exclude foundation, land and tower construction, and the sheet says microwave networks still need fibre backhaul. — [NTIA, Costs at a Glance](https://broadbandusa.ntia.doc.gov/sites/default/files/resource-files/bbusa_costs_at_glance_networks.pdf) (date not confirmed in the result)
- Tower space: about US$400/month plus US$100 per linear foot of antenna, so a link between two 4-foot antennas costs about US$1,600/month (2014, historical). — [RCR Wireless, Microwave Link Design](https://rcrwireless.com/20140513/fundamentals/microwave-link-design)
- Anecdotal forum quote: US$550/month on a 5-year lease with 3% annual escalation and a US$2,000 structural analysis fee. Not representative. — [MikroTik forum, tower lease pricing](https://forum.mikrotik.com/t/tower-lease-pricing/73459)
- A 2024 analyst note: microwave typically has lower deployment cost than wired backhaul, but CSPs are increasingly concerned about recurring tower-related rental costs (OPEX). — [RCR Wireless, 2024 analyst angle](https://www.rcrwireless.com/20240903/5g/microwave-technology-continues-to-evolve-to-meet-the-challenges-of-5g-and-ai-data-requests-analyst-angle)
- Ericsson (2026): where fibre is not already at the cell site, deployment cost can be significantly higher than a microwave link. — [Ericsson blog, 2026](https://www.ericsson.com/en/blog/middle-east-africa/2026/microwave-is-the-new-fiber-rethinking-5g-backhaul) (search summary; page not fetched)
- Vendor claim (BridgeWave, promotional): fibre at US$24.50 per linear foot is about US$130,000 per mile. — [BridgeWave](https://bridgewave.com/?p=2222)
- Nebraska Public Service Commission filing: about US$69,013 per tower for a wireless broadband upgrade including backhaul, access point, cabinet and labour. Not a standalone link cost, so not directly comparable. — [AMG Technology, Attachment H](https://psc.nebraska.gov/sites/psc.nebraska.gov/files/doc/AMG%20Technology_Wireless%20North_Attachment%20H_Project_Costs_0.pdf)
- FCC coordination: see Key Question 1 (applicants coordinate before filing; ULS filing). Processing time was not found. A 1996 source names the Wireless Telecommunications Bureau Licensing Division (Gettysburg, PA) as processing office for Part 21/94 microwave (historical). — [FCC 96-51A1](https://apps.fcc.gov/edocs_public/attachmatch/FCC-96-51A1.pdf) (search result)

### Inferences
- Tower rent is a recurring cost that can rival or exceed the one-off equipment cost over a multi-year horizon, but no current benchmark was verified. A 2014 rate of US$1,600/month for a two-antenna link implies roughly US$19,000 per year per link.
- Vendor and filing figures cannot be combined into a reliable all-in per-link estimate without current quotes.

### Gaps
- No verified 2025–2026 equipment cost per link (radio pair, antennas, installation) in USD, GBP or EUR.
- No verified Ofcom or FCC licence fee per link for 2026. The Ofcom wireless telegraphy licence charges amendment for 2027 was proposed (per search result) but figures were not retrieved.
- No verified coordination timeline (weeks or months) for FCC Part 101 or Ofcom fixed-link applications.
- No current tower-lease rate card from a major tower company (e.g. American Tower, Cellnex, IHS, Indus) was found.

---

## Key Question 3: Where is microwave backhaul used (rural broadband, 5G backhaul, emergency networks)?

### Takeaway
Evidence for current use is strongest for 5G and LTE backhaul, where Ericsson reports microwave as a major transport medium and its outlook projects near-parity with fibre. Rural and emergency examples found are mostly vendor case studies or dated (2011–2014). No independent 2025–2026 Africa or India microwave deployment case study with cost or coverage outcomes was found.

### Cited Findings
- India (vendor, Nokia): case study with an unnamed major Indian operator keeping high-capacity E-band links running in heavy rain. — [Nokia, E-Band microwave backhaul performance under heavy rainfall](https://www.nokia.com/asset/213320/) (vendor-authored)
- India (vendor, Huawei): an Indian operator moved its bearer network from 3G to 4G and needed to multiply microwave capacity; a second operator faced similar pressure but had no spare microwave spectrum. — [Huawei, 5G microwave fast-track for emerging markets](https://www.huawei.com/en/huaweitech/publication/winwin/32-extra/5g-microwave-fast-track-mbb-growth-emerging-markets) (vendor-authored; date not confirmed)
- Africa (academic): a Tanzania techno-economic analysis compares microwave with broadband over power lines for rural backhaul. Findings not visible in the search result. — [ajol.info, IJEST article](https://ajol.info/index.php/ijest/article/view/257830/243513)
- Africa (Microsoft research): TV white spaces combined with point-to-point microwave links to serve remote African regions (hybrid architecture). — [Microsoft Research paper](https://microsoft.com/en-us/research/wp-content/uploads/2016/02/main-5.pdf)
- Rural NLOS/CLOS: Meta Connectivity research on combining line-of-sight and non-line-of-sight microwave for dispersed rural settlements, and a techno-economic model for diffractive NLOS links in Peru, Kalimantan and Papua. — [Meta research, CLOS/NLOS](https://research.facebook.com/file/3015387262008106/Combining-CLOS-and-NLOS-Microwave-Backhaul-to-Help-Solve-the-Rural-Connectivity-Challenge.pdf); [Meta research, e3nb model](https://research.facebook.com/file/526285882141305/Engineering-Economic-Evaluation-of-Diffractive-NLOS-Backhaul-(e3nb)--A-Techno-economic-Model-for-3D-Wireless-Backhaul-Assessment.pdf) (company-authored)
- Emergency/public safety: microwave backhaul carries 911 traffic. Will County, Illinois connected a new dispatch centre about 13 miles from a regional switch using Exalt microwave (2011, historical; vendor announcement). — [RCR Wireless, Exalt / Will County](https://www.rcrwireless.com/20110727/wireless/exalt-provides-communication-to-will-county-ill-emergency-services)
- FirstNet/PSCR: Aviat microwave radios completed LTE trials validated for public-safety LTE capacity (2014, historical). — [RCR Wireless, Aviat FirstNet](https://www.rcrwireless.com/20140304/uncategorized/aviat-completes-lte-microwave-solutions-trials-ready-for-firstnet-launch-3)
- Public safety migration: agencies are replacing legacy dedicated backhaul with packet microwave plus IP/MPLS as they move to LTE and 5G (vendor framing; Nokia MPSCS deployment referenced). — [Nokia, MPSCS deployment](https://nokia.com/index%2ephp/customer-success/mpscs-deploys-nokias-ipmpls-and-packet-microwave-technology)
- Ericsson (2025) states that the global backhaul market is shifting toward a near-equal microwave/fibre split, 49% microwave and 51% fibre by 2030 (forecast). — [Computer Weekly, Backhaul shows near-equal split](https://www.computerweekly.com/news/366632858/Backhaul-shows-near-equal-split-between-fibre-wireless); [Ericsson Microwave Outlook 2025 news](https://www.ericsson.com/en/news/2025/10/microwave-outlook-2025-near-fiber-split-ai-and-2x-capacity)

### Inferences
- Microwave is positioned as the fast-to-deploy option where fibre is absent, and as a converged IP/MPLS transport layer in public safety. Both points rest on vendor material.
- Rural and African uptake is likely driven by the NLOS/TVWS hybrids and by fibre cost, but no independent 2025–2026 data confirms adoption levels.

### Gaps
- No independent 2025–2026 Africa operator case study with per-link cost, uptime or coverage figures (e.g. from GSMA, World Bank or a national regulator).
- No 2025–2026 public-safety microwave deployment was confirmed in search results (FirstNet and PSCR material found is from 2014).
- The Tanzania TEA results and the Huawei India case figures were not retrieved in full.

---

## Key Question 4: How does microwave compare with fibre and satellite backhaul; deployment trends?

### Takeaway
Ericsson projects microwave and fibre at near-parity by 2030 (49% microwave / 51% fibre), and Ericsson's 2026 messaging is that microwave is the "new fibre" for 5G backhaul. Satellite holds a small share of backhaul links and is economically sensitive to bandwidth price. Cost comparisons rely on dated or vendor data.

### Cited Findings
- Ericsson Microwave Outlook 2025 (Oct 2025): near-equal split projected by 2030, microwave 49% and fibre 51%. The 49/51 figure is a forecast, not a 2025 measurement. — [Computer Weekly](https://www.computerweekly.com/news/366632858/Backhaul-shows-near-equal-split-between-fibre-wireless); [Ericsson news](https://www.ericsson.com/en/news/2025/10/microwave-outlook-2025-near-fiber-split-ai-and-2x-capacity)
- Light Reading reports that most backhaul is currently microwave, with fibre gaining share in dense urban areas. — [Light Reading](https://www.lightreading.com/5g/e-band-fit-to-provide-microwave-backhaul-for-years-says-ericsson) (search summary; primary figure not confirmed)
- Ericsson Mobility Report (June 2025): mobile data traffic growing about 15% year on year. A later Microwave Outlook (per search summary) cites a 22% rise between Q1 2025 and Q1 2026; not verified. — [Ericsson Mobility Report, June 2025](https://www.ericsson.com/mobility-report/2025)
- Satellite share: a figure of 1.9% of backhaul links worldwide, attributed to ABI Research via GSMA, with fibre and microwave each around 38–40% of macro sites. Date and primary source not confirmed. — [GSMA, Mobile Backhaul Options](https://www.gsma.com/spectrum/wp-content/uploads/2019/04/Mobile-Backhaul-Options.pdf) (2019 document; may not contain this figure)
- Satellite economics (Analysys Mason, 2022): NPV becomes negative for the sample case if bandwidth cost exceeds US$65 per Mbit/s per month; the authors flag their fibre assumption of US$8,000 per km as possibly misleading. — [Analysys Mason, backhaul quarterly](https://analysysmason.com/about-us/news/newsletter/backhaul-satellite-fibre-quarterly/article-pdf) (2022, historical)
- LEO satellite backhaul costs were expected to fall with more constellations (Internet Society, 2019, historical). — [Internet Society, community network backhaul](https://internetsociety.org/resources/doc/2019/solutions-for-traffic-backhaul-in-community-networks/)
- Capacity: a LinkedIn post claims E-band systems deliver up to 20 Gbps per link. Not authoritative; treat as unverified. — [LinkedIn post](https://ca.linkedin.com/in/malakjc)
- Chalmers University TCO study compares microwave and fibre 5G transport; numbers not retrieved. — [Chalmers research, publication 535216](https://research.chalmers.se/publication/535216/file/535216_Fulltext.pdf)

### Inferences
- Microwave's cost advantage over fibre is strongest where fibre is absent (new build over distance). Where fibre already exists, the economics favour fibre.
- Satellite is a niche rural option, sensitive to bandwidth pricing. The 1.9% figure, if correct, implies a very small role.
- Recurring tower rent and capacity upgrades (E-band, 2x capacity per Ericsson's 2025 framing) are the main cost drivers in the 2026 trend.

### Gaps
- No verified 2025–2026 all-in cost comparison (microwave vs fibre vs satellite) per site or per km.
- The Chalmers TCO results were not retrieved.
- The satellite backhaul share (1.9%) and the 38–40% macro-site split were not confirmed against a primary source dated 2025–2026.
- No 2026 Dell'Oro, Omdia or GSMA microwave market-size or share figure was retrieved.

---

## Source Notes and Next Steps
- Re-check the Ofcom fixed-link and light-licensing pages, FCC Part 101 (eCFR), and the FCC 25-70 and 2025-21805 documents once the host is reachable (www.ofcom.org.uk, www.fcc.gov, www.ericsson.com are blocked by the session network).
- Priority gaps for a follow-up pass: current per-link licence fees (Ofcom and FCC), coordination timelines, a 2025–2026 cost benchmark per link, and a 2025–2026 Africa/India operator case study (GSMA, World Bank, operator reports).
