# Delta's public turnaround/FOD flow, the vendor landscape, and the PoC offer

Research for ticket 0017 (`issues/0017-delta-flow-and-poc-offer.md`). Retrieved 2026-11-13. Feeds the requirements baseline (0016).
Builds on `research/gate-turnaround-fod-workflow.md` (the 15-step workflow table, cited here as **WF #n**), `research/faa-fod-guidance.md`, `spec/fod-rules.md`, `spec/inspection-report-schema.md` and `prototypes/local-detect/RESULTS.md`.
**Out of scope here:** ATL Concourse T gate layout, gate numbering and who staffs which ATL ramp tower. Those are in `research/atl-concourse-t-site.md` (ticket 0015).

**Source labels.** **[P]** = primary: Delta's own pages, the vendor or airport speaking for itself, FAA, Federal Register. **[S]** = secondary: trade press, news, aggregators. **[V]** = a vendor's claim about its own product, which is primary for *what is offered* but not independent evidence that it *works*. Individuals quoted in sources are identified only by role.

## Sources

| Short name | Document | Label | URL |
|---|---|---|---|
| **Delta ramp 2025** | Delta News Hub, "Delta spurs innovation on the world's busiest ramp", 3 Dec 2025 (updated 23 Sep 2026) | P | https://news.delta.com/delta-spurs-innovation-worlds-busiest-ramp |
| **Delta ESG SMS 2025** | Delta, *2025 Delta Difference* report, Safety Management System page | P | https://esghub.delta.com/content/esg/en/2025/safety-management-system.html |
| **Delta ESG EmpSafety 2025** | Same report, Employee Safety Programs and Training | P | https://esghub.delta.com/content/esg/en/2025/employee-safety-programs-training.html |
| **Delta ESG AI 2025** | Same report, Responsible approach to AI | P | https://esghub.delta.com/content/esg/en/2025/responsible-approach-to-ai.html |
| **IATA Delta 2026** | IATA *Safety Leadership in Practice*: Delta, 30 Apr 2026 | P (IATA, Delta-supplied) | https://www.iata.org/en/programs/safety/safety-leadership/safety-leadership-in-practice/delta-apr-2026/ |
| **Schiphol DT-Delta** | Schiphol Aviation Solutions blog, "How Delta uses Deep Turnaround", 17 Jun 2025 | P (vendor/airport with Delta staff quoted) | https://www.schiphol.nl/en/aviation-solutions/blog/from-endless-calls-to-a-streamlined-operation-how-delta-uses-deep-turnaround |
| **Schiphol DT** | Deep Turnaround, "How it works" | V | https://www.schiphol.nl/en/aviation-solutions/deep-turnaround-how-does-it-work |
| **NPR 2026** | NPR, "Inside ATL: how Delta juggles 100,000 bags a day", 26 May 2026 | S | https://www.npr.org/2026/05/26/nx-s1-5801537/atl-airport-atlanta-baggage-handling-delta |
| **ATL CIO 2026** | International Airport Review, article by ATL's CIO, 31 Jul 2026 | P (airport official, trade venue) | https://www.internationalairportreview.com/computer-vision-and-ai-overlays-at-scale-building-the-foundations-for-real-time-airport-operations/2135984.article |
| **AJC 2025** | AJC, "How AI is revolutionizing ATL's international terminal", Jun 2025 | S | https://www.ajc.com/business/2025/06/how-ai-is-revolutionizing-atls-international-terminal |
| **AW SWA 2023** | Aviation Week, "Southwest Airlines Expanding Atlanta Turnaround Tech Trials To Denver", 13 Dec 2023 (paywalled; lead paragraph read) | S | https://aviationweek.com/air-transport/airlines-lessors/southwest-airlines-expanding-atlanta-turnaround-tech-trials-denver |
| **Assaia Solutions / FAQ** | assaia.com/solutions (product list and FAQ) | V | https://www.assaia.com/solutions |
| **Assaia SafetyControl** | assaia.com/solutions/safetycontrol | V | https://www.assaia.com/solutions/safetycontrol |
| **Assaia SMS** | assaia.com, "FAA mandates SMS" | V | https://assaia.com/resources/faa-mandates-sms |
| **Assaia 1M** | assaia.com, "Assaia celebrates millionth turn", 13 Nov 2024 | V | https://assaia.com/resources/topping-the-turnaround-tables-assaia-celebrates-millionth-turn |
| **YYC 2025** | Calgary Airport Authority, ApronAI across 67 gates, 29 Oct 2025 | P | https://www.yyc.com/en-us/media-centre/blog/artmid/1030/articleid/174/assaia-partners-with-calgary-international-airport-to-deploy-apronai-across-67-gates-driving-on-time-performance-and-efficiency |
| **JFKIAT 2021** | JFKIAT press release (republished by AviationPros), 29 Nov 2021 | P via S | https://www.aviationpros.com/ground-support-worldwide/gse/gse-technology/press-release/21248248/ |
| **LAS 2024** | Assaia release on Harry Reid (LAS) via Saab Aerobahn, 30 Oct 2024 (republished) | P via S | https://www.aviationpros.com/ground-support-worldwide/ground-handling/press-release/55239366/assaias-apronai-to-be-deployed-at-las-vegas-harry-reid-airport |
| **PIT Synaptic** | Pittsburgh International Airport, "AI platform for airport operations" (c. 2025) | P | https://flypittsburgh.com/ai-platform-for-airport-operations |
| **Synaptic brochure** | Synaptic Aviation one-pager (PTE World exhibitor library) | V | https://cdn.asp.events/CLIENT_CloserSt_D86EA381_5056_B739_5482D50A1A831DDD/sites/PTEWorld/media/libraries/exhibitor-brochures/824818-one-pager-aviation-brochure.pdf.pdf |
| **DFW A9** | AviationPros, "The Intelligent Airport Apron Becomes Reality" (DFW gate A9 trial) | S | https://www.aviationpros.com/directory/airport-facilities-buildings/article/53042337/airport-intelligent-apron-technology |
| **ADB AiPRON FOD** | ADB SAFEGATE *AiPRON FOD* brochure, 2025 (PDF read in full) | V | https://adbsafegate.com/media/w3yk34hl/adb-safegate_fod_brochure-2025.pdf |
| **ADB+Assaia 2021** | ADB SAFEGATE press release, Safedock cameras + ApronAI pilots, Jan 2021 | P | https://adbsafegate.com/news-events/press-releases/adb-safegate-teams-up-with-assaia-to-make-data-driven-airside-operations-a-reality/ |
| **ArgosAI** | argosai.com home and company pages | V | https://argosai.com/ |
| **TPA Overwatch** | International Airport Review, Tampa International's Overwatch apron programme, 11 Sep 2026 | S (airport-authored content) | https://www.internationalairportreview.com/digital-and-automation/how-tampa-international-airport-is-bringing-operational-certainty-to-the-modern-apron/2136441.article |
| **Sotereon 2025** | Business Wire, "Sotereon.AI Expands to Tampa", 27 Oct 2025 | P | https://www.businesswire.com/news/home/20251027367342/en |
| **QinetiQ Tarsier** | QinetiQ, Automatic FOD detection | V | https://www.qinetiq.com/en/markets/aviation-and-aerospace/automatic-foreign-object-debris-detection |
| **BOS FODetect** | Xsight press release (AviationPros), Nov 2013; KSL/AP coverage | P via S | https://www.aviationpros.com/airport-business/airport-infrastructure-operations/airports-municipalities/press-release/11234714/ |
| **CAG iFerret** | International Airport Review, Changi Airport Group FOD detection | S | https://www.internationalairportreview.com/article/182568/changi-airport-group-runway-safety-fod-detection-technology |
| **FAA Trex** | FAA Airport Technology R&D, performance assessment of a mobile radar FOD system | P | https://www.airporttech.tc.faa.gov/Products/Airport-Safety-Papers-Publications/Airport-Safety-Detail/performance-assessment-of-a-mobile-radar-based-foreign-object-debris-detection-system |
| **Part 139 SMS** | Federal Register, *Airport Safety Management System* final rule, 88 FR 11642, 23 Feb 2023 | P | https://www.federalregister.gov/documents/2023/02/23/2023-03597/airport-safety-management-system |

**Looked for, not obtained**
- **Any Delta FOD program, procedure or campaign.** Searched the News Hub, ESG hub and TechOps material. None found. The 2025 ESG safety pages do not mention FOD.
- **A current Delta turn-time target.** The only Delta figures found are from 2005 (below).
- **Any Delta gate-camera, apron computer-vision or "smart ramp" pilot at a US station.** None found. The only Delta apron computer-vision use found is at Amsterdam (Deep Turnaround, below).
- **The Delta 10-K text on AI.** Only the ESG page wording was read. Aggregators paraphrase the 10-K the same way.
- **Vendor pricing.** No camera-AI vendor publishes prices. The only public figures are grants and old runway-system costs (table below).
- **ADB SAFEGATE product page** returned 403. The 2025 brochure was read instead.

## 1. Delta's public flow and programs

### 1.1 Ramp control and the turn at ATL
- **Delta runs its own ramp control model in the US.** Schiphol's 2025 case study says: "In Atlanta, Delta already operated [a] domestic control tower ... to ensure safe and efficient arrivals and departures", and this "inspired Delta in 2019 to set up the same for EMEA". It also says "At its domestic hubs in the U.S., Delta has full control over its operational processes" [P, Schiphol DT-Delta]. A 2014 visit to Delta's ATL ramp tower describes controllers telling aircraft when to push, then handing them to FAA ground [S, AirlineGeeks 2014]. Who staffs each ATL ramp tower today is left to 0015.
- **Turn-time targets: nothing current is public.** In 2005 Delta ran "Operation Clockwork" in Atlanta to cut turn times, with a second phase planned to cut "five more minutes" [S, Aviation Week, 26 Jul 2005]. A 2005 report gives a 45-minute narrowbody minimum ground time [S, NBC News]. Both are 20 years old. OAG's March 2023 data puts planned average turns for US majors at 52–68 minutes [S, OAG blog]. **For 0016:** don't assume a turn-time target. Treat Inspection latency (about 12–17 s, RESULTS.md) as a budget to confirm with Delta.

### 1.2 Digital ramp tools Delta has announced (all at ATL unless noted)
| Tool | Status and date | What it does | Source |
|---|---|---|---|
| **Baggage AI** (built in-house) | **Deployed** at ATL (article 3 Dec 2025). Expansion to DTW and MSP "later this year" (NPR, May 2026) | Routes about 250 bag-transfer drivers like a ride-hail app. Recalculates every 2 minutes. About 30% improvement in bag transfers (Delta). NPR quotes Delta as "as much as 20%" | P Delta ramp 2025; S NPR 2026 |
| Baggage AI autonomous dispatch, transfer-driver bag scanning | **Announced for 2026** | Assign drivers to nearby tasks; new tracking points | P Delta ramp 2025 |
| **Autonomous jet bridges**, Concourse B | **Deployed.** More than 1,100 flights with no aircraft damage or injury (as of Dec 2025) | Delta calls it "the first in commercial aviation" | P Delta ramp 2025 |
| **Autonomous bag tugs**, Cargo and **Concourse T bag room** | **Deployed since 2023.** 4,000 miles, zero injury or damage incidents. 15 expected by end of 2025 | — | P Delta ramp 2025 |
| $110M bag-system link between Concourses B, C, T | In progress. $40M spent in 2025 | — | P Delta ramp 2025 |
| AI for **gating decisions** and short-connection bags | Stated as operational initiatives (2025 report) | — | P Delta ESG AI 2025 |
| **GSE collision-avoidance systems**, power stows, ground A/C units | Investments in 2025 | Ramp safety equipment | P Delta ESG SMS 2025 |
| AI to analyse **operational safety reports** | In use (2025) | Faster, more consistent coding of reports | P Delta ESG SMS 2025 |
| **Deep Turnaround at Amsterdam (AMS)** | **In use, "a standard tool in Delta's daily workflow"** (17 Jun 2025). AMS is an airport-provided system, not a Delta purchase | Delta's AMS tower uses live stand video plus an AI event timeline. About 30 min before departure staff check "Is there any equipment blocking the aircraft?" Unnecessary calls cut by half | P Schiphol DT-Delta |

**Most relevant line found for this PoC.** In the AMS case study Delta "sees even more ways AI can help, like **automatically spotting safety hazards on the ramp, such as oil spills or misplaced equipment**" [P, Schiphol DT-Delta, Jun 2025]. That is a stated wish, not a deployment. It is the only public Delta statement linking ramp cameras to hazard detection.

**What the airport (not Delta) runs at ATL.**
- The City of Atlanta has run Saab **Aerobahn** surface management since 2010 (renewed and expanded around 2014) [S, Aviation Today 2014].
- ATL started a pilot in June 2025 overlaying computer vision on its security cameras [S, AJC 2025]. By 31 Jul 2026 the CIO reports "AI-enabled overlays across nearly 2,000 cameras", deployed on-premises. The use cases are security and operations: unattended bags, restricted-area access, curbside [P, ATL CIO 2026]. **No apron, ramp or FOD use case is stated.**
- The only apron camera-AI trial found at ATL is **Southwest's** Assaia ApronAI on 18 ATL gates, reported 13 Dec 2023 and expanding to 14 Denver gates [S, AW SWA 2023]. Southwest later cut ATL to 11 gates (2024) [S, Fortune]. Whether ApronAI is still running at ATL is **unknown**.

### 1.3 Safety management and culture
- **SMS.** Delta keeps "an FAA-approved safety management system", covering both occupational and operational safety. It applies safety risk management to changes such as new procedures [P, Delta ESG SMS 2025]. That is the Part 5 SMS from WF §1. A new FOD tool at the gate would be a change that Delta's SRM assesses.
- **Reporting.** ASAP (confidential reporting). Voluntary hazard reporting for about 90,000 frontline employees. **128,511 safety reports in 2025.** LOSA began in 2025. Internal Evaluation Program [P, Delta ESG SMS / EmpSafety 2025].
- **Stop-work authority.** "Any employee or contractor may call a **Safety Time Out** to pause to correct a safety issue" [P, Delta ESG SMS 2025]. IATA's case study: "Call a safety timeout if you need to." Safety leadership is formalised as the fifth element of Delta's SMS ("Intentional Safety Culture"). Annual Safety Day (June) and Safety & Environmental Summit (May, includes "aircraft damage prevention") [P, IATA Delta 2026; Delta ESG EmpSafety 2025].
- **Human in the loop is Delta's stated stance.** "A human is always present in the safety system to ensure the quality of reporting and analysis" [P, Delta ESG SMS 2025]. On the ramp: "We don't see AI as something that is going to replace our people ... We see AI as an enabler" (Delta ATL operations director) [S, NPR 2026]. AI governance runs through an AI Governance Committee, with Board oversight via the Audit Committee [P, Delta ESG AI 2025].
- **Metrics.** DART 3.32, TRIR 4.02 (2025), total recordable injuries down 3% since 2024 [P, Delta ESG EmpSafety 2025]. No FOD or ground-damage metric is published.
- **FOD specifically.** No public Delta FOD campaign or procedure. Old trade items note Delta at the National FOD Prevention Conference [S, fodnews.com, undated]. This matches WF "Looked for, not obtained".
- **Airport SMS context.** The FAA's Airport SMS rule (Part 139, published 23 Feb 2023, effective 24 Apr 2023) requires SMS at certain certificated airports, including hubs [P, Part 139 SMS]. Its apron scope was not checked here. Assaia markets ApronAI as feeding airport SMS data [V, Assaia SMS].

**Implications for the PoC pitch.**
1. Delta builds in-house (Baggage AI) and already uses stand video at AMS. The pitch should be an add-on that produces findings and records Delta's tower and SMS can take in, not a turnaround platform.
2. Safety Time Out, and "a human is always present", match the PoC's rules: the Verdict is advisory until confirmed, and only the Ramp Lead clears a HOLD.
3. "Misplaced equipment" and "oil spills" are Delta's own words. They map to FOD-R9 (GSE staging) and FOD-R7 (non-FOD observations).

## 2. Vendor landscape

"Detects": **M** = turnaround milestones/timestamps; **S** = safety/SOP events (people, PPE, cones, speeding, jet bridge); **P** = *process* verification (was a check done); **F** = FOD/debris on the surface; **E** = equipment staging/stand clear.

| Product (vendor) | Detects | Sensing | Deployments (US / ATL / Delta flagged) | Integration | Pricing (public) |
|---|---|---|---|---|---|
| **ApronAI, TurnaroundControl, SafetyControl** (Assaia) | M; S (speeding, unauthorized persons, PPE, chocks/cones, "aerobridge not fully parked"); **P**: "can also support the process of FOD check and determine whether it was performed properly"; **E**: "determine if the stand is clear for an aircraft to enter" [V] | Existing fixed cameras, 1–3 per stand, 15–20 m mount preferred, no PTZ movement [V, FAQ] | >20 airports (Nov 2024) [V, 1M]. **US:** SEA with Alaska (in Aerobahn), JFK T4 (from Nov 2021) [P via S], CVG, LAS via Saab Aerobahn (announced 30 Oct 2024) [P via S], Breeze (up to 30 gates, phase 1) [S]. Southwest **ATL 18 gates trial**, Dec 2023 [S]. YYC 67 gates (rollout from 31 Jul 2025) [P]. **Delta: no confirmed deployment** (JFK T4 is a Delta terminal, but the release names no airline) | Major VMS providers, cloud or on-prem [V]. A-CDM/TOBT feeds [V]. YYC runs on AWS [P]. Safedock VDGS camera pilots (Jan 2021) [P] | Not public. YYC got C$1.1M from Transport Canada toward its project [P] |
| **Deep Turnaround** (Royal Schiphol Group) | M; lists safety value cases "cones placed, fuelling after passenger disembarked, stand cleared, **FOD detection**" [V] | 2 cameras per stand, snapshot to cloud every 5 s [V] | AMS and "multiple airports" [V]. **Delta AMS tower uses it daily** (Jun 2025) [P] | Stand-alone dashboard and API; TOBT/CDM [V] | Not public |
| **Synaptic Aviation** | M; S (cones missing, vests missing, "obstacles inside the safety zone", "gates aren't clear, crews missing"); claims "From FOD to safety zone violations" [V] | Gate cameras (PIT: "cameras stationed at a gate") [P] | **US:** PIT with IAG, 3 common-use gates, "proof of concept ... expanded testing in progress" (c. 2024–25) [P]. DFW gate A9 with American and ADB SAFEGATE, trial Sep–Nov (year not stated, c. 2021) [S]. EZE 60+ cameras after 90-day PoC [S]. "~1,000 gates" claimed [S]. No ATL or Delta | Not detailed | Not public |
| **AiPRON FOD** (ADB SAFEGATE) | **F** on the apron, "down to 3x3x3 cm", up to 100 m from camera; tells vehicles, wildlife and FOD apart; alarm with timestamp, location, image, size [V, brochure] | "AI-powered detection, and advanced sensors". Trade press says cameras plus radar [S] | None named in brochure. No US deployment found | "Fully integrates with apron management systems". Web HMI. Pairs with Safedock A-VDGS [V] | Not public |
| **A-PAC, A-FOD, A-PASS** (ArgosAI) | **F + E pre-arrival**: "A-PAC automates FOD and stand-clearance checks before aircraft arrival ... debris and misplaced equipment" [V] | Camera imagery [V] | Founded 2015. "7 major airports, 27 devices". Logos: Gatwick, Heathrow, Istanbul [V]. No US deployment found | Sends clearance status to integrated VDGS [V] | Not public |
| **Overwatch** (Sotereon.AI, with Tampa International) | Planned: underwing safety (engines, fuelling, chocks, wing walkers); **pre-arrival gate inspection: FOD, obstructed lead-in, staged GSE, people in prohibited areas**. FOD is an "early advisory function" (phase 3 of 5) [S] | **LiDAR** + AI + telemetry [P, Sotereon 2025] | **US: TPA**, relationship since 2023, 7-year agreement [S]. Which phase is live is not stated. No Delta | Plan-vs-observed against "an approved operational plan"; work orders [S] | Not public |
| **Aerobahn** (Saab) | Surface movement, A-CDM, de-icing; a host for ApronAI (SEA, LAS) | Surveillance feeds | **ATL (City of Atlanta) since 2010** [S] | Integration hub | Not public |
| **Tarsier** (QinetiQ) | **F on runways** | Millimetre-wave radar + zoom camera to confirm | YVR, LHR, DXB, DOH. FAA evaluation at PVD [V/S] | Ops-centre alarm with location | Not public |
| **FODetect** (Xsight) | **F on runways** | Radar + EO on edge-light fixtures every 200 ft | **US: BOS runway 09-27, Nov 2013** (first US), SEA (vendor claim, 2017) [P via S] | Ops alerts | BOS cost **$1.7M** (FAA and Massport funded) [S] |
| **iFerret** (Changi Airport Group / NCS) | **F on runways**, down to 2 cm in rain (trial) | EO cameras + ML | SIN (since about 2009; v2.0 on Runway 3), DXB. ORD listed [S] | Ops alerts | Not public |
| **FOD Finder** (Trex) | **F**, mobile sweep | Vehicle-roof mm-wave radar + IR | FAA-assessed from 2008 at ORD [P]. Navy/Marine air stations [S] | Vehicle HMI, vacuum retrieval | ~$400k, or $12–15k/month lease (c. 2016) [S] |

**Takeaways.**
- **Turnaround vendors** (Assaia, Deep Turnaround, Synaptic) are well deployed in the US, ATL included, via Southwest's trial. They time events and flag SOP deviations. On FOD they mostly offer **process verification** (did the check happen) or a generic "stand clear". Assaia found post-departure stand checks skipped on almost 60% of flights in week one, falling to 24% [V, Assaia SMS]. None publishes a per-item debris Finding with a severity or a rule basis.
- **Apron debris detectors** (ADB AiPRON FOD, ArgosAI A-PAC, TPA Overwatch) are the closest competitors. ADB and ArgosAI have **no public US deployment**. Overwatch is US (TPA) but uses LiDAR, and its FOD function is a roadmap phase.
- **Runway FOD systems** (Tarsier, FODetect, iFerret, FOD Finder) cover the **movement area** and are the airport's equipment. They are the right home for WF #14 movement-area escalation, not for the gate. FAA's AC 150/5220-24 rates the apron lowest priority for detection equipment (`research/faa-fod-guidance.md`).

## 3. Capability matrix: 15 workflow steps × PoC role × existing products

PoC role: **Automate** = the PoC performs the check and gives a Finding or Verdict. **Verify** = the PoC gives image evidence that a human step happened or its outcome holds, at capture time. **Record** = the PoC keeps the audit record. **None** = not in PoC scope.

| WF # | Step | PoC role | How (rule / schema) | Existing products covering it |
|---|---|---|---|---|
| 1 | Pre-arrival briefing | **None** | — | None |
| 2 | **Pre-arrival FOD walk** | **Automate + Record** | `pre_arrival` Inspection across 6 Angles. FOD-R1–R5 by tier × class. Confirmed-clean frame becomes the change-detection reference | ArgosAI A-PAC (F+E, VDGS) [V]; ADB AiPRON FOD (continuous F) [V]; Overwatch pre-arrival inspection (roadmap) [S]; Deep Turnaround lists "FOD detection" [V]; Assaia: *was the check performed* [V] |
| 3 | Stand surface condition | **Record** (outside Verdict) | FOD-R7 `observations` (snow_ice, live_wildlife). **Spills not yet a kind** (gap) | None found. Delta AMS wants oil-spill spotting (wish) [P] |
| 4 | **GSE, chocks, cones outside ERA** | **Automate** | FOD-R9 `equipment_staging` REMOVE at pre-arrival; needs the ERL mapped per Gate | ArgosAI ("misplaced equipment") [V]; Overwatch ("staged ground equipment") [S]; Synaptic ("obstacles inside the safety zone") [V]; Assaia ("stand clear") [V]. Delta AMS does it by eye on Deep Turnaround video [P] |
| 5 | Docking/marshaller, 2 wing walkers (ATL) | **None** | People detection out of scope | Synaptic ("crews missing") [V]; Overwatch (wing walkers) [S]; VDGS (ADB Safedock) |
| 6 | Block-in: no approach until stop, engines off, beacon off, chocks | **None** | No block-in Inspection (0005 amendment) | Assaia SafetyControl (people near aircraft, chocks/cones) [V]; Deep Turnaround ("cones placed") [V]; all turnaround vendors timestamp on-block |
| 7 | GSE full stop before ERA | **None** | — | Assaia (speeding; 38.5% of pushbacks with violations, vendor study) [V] |
| 8 | Clean-as-you-go; bag/cargo area | **Verify** (on demand) | `on_demand` Inspection of CARGO/AFT; FOD-R3 | ADB AiPRON FOD (continuous) [V]; turnaround vendors time loading but don't look for debris |
| 9 | Equipment removed, doors, jet bridge retracted, GSE out | **Verify** (partial) | Jet bridge state and GSE vs ERL in WIDE trigger and support the pre-departure Inspection; FOD-R8/R9 | Assaia ("aerobridge not fully parked" SOP alert) [V]; all turnaround vendors timestamp bridge-off/GSE-off |
| 10 | **Pre-departure FOD walk / 360°** | **Automate + Record** | `pre_departure` Inspection; FOD-R1–R6; INCOMPLETE if an Angle is unusable (R6) | ADB AiPRON FOD (continuous) [V]; Assaia (was the stand check performed) [V]. **No product found that publicly gives a per-Angle pre-push FOD Verdict** |
| 11 | Engine ingestion/blast zones clear | **Verify** (at capture only) | ENG-L/ENG-R must be usable; FOD-R1 HOLD. People/GSE in zone is shown, not continuously monitored | Assaia (unauthorized persons near aircraft) [V]; Overwatch (engines, underwing) [S] |
| 12 | Headset comms; push team briefed | **None** | — | None |
| 13 | **Clear any HOLD**, then tell flight crew | **Record** (+ Verify via re-inspection) | Confirmation `removed` / `false_alarm` / `not_found_on_walk`; **only `ramp_lead` may confirm a HOLD**; optional after-photo or `on_demand` re-inspection | **None found with role-gated confirmation.** ArgosAI pushes clearance to VDGS [V]; Overwatch "declare[s] readiness" [S]. Both are automatic, not human-confirmed |
| 14 | Escalate FOD outside the envelope | **Record + route** | FOD-R10, `zone_tier: outside_boundary`, `responsible_party`; routed to ramp control and/or Airport Ops per LOA | Runway systems for the movement area (Tarsier, FODetect, iFerret, FOD Finder); ADB/ArgosAI to apron management [V] |
| 15 | Post-departure stand check | **Verify (optional)** | Could reuse a `pre_arrival`-style capture as the next reference | Assaia measures whether it was skipped (60% → 24%) [V] |

**Count (by primary role):** the PoC automates 3 steps (2, 4, 10), verifies 4 (8, 9, 11, 15), records 3 (3, 13, 14) and has no role in 5 (1, 5, 6, 7, 12). Steps 2 and 10 are also recorded, and 13 is also verified by re-inspection. The steps it skips are the people/SOP-event steps where turnaround vendors are strongest.

## 4. Differentiation and gaps

### Where the PoC is differentiated (evidence-based)
1. **Debris Findings, not milestones or process checks, on cameras already at the gate.** Deployed US turnaround vendors (Assaia, Synaptic, Deep Turnaround) check that the FOD check *happened*, or that the stand is "clear". The PoC returns each object with bbox, zone tier, category, size and severity. The apron debris products that do this (ADB, ArgosAI) have no public US deployment. Overwatch's FOD is a roadmap phase on LiDAR.
2. **Rule-traceable output.** Every Finding carries `rule_id` (FOD-R1…R10) tied to FAA AC 150/5210-24A, IGOM 4.1.1 and ATL rules (`spec/fod-rules.md`). Severity is computed in code from tier × class (RESULTS.md recommendation 5). Vendors claim only to "align with ICAO and FAA standards" [V, ADB]. No vendor found publishes a rule-cited severity.
3. **Human-confirmed, role-gated audit trail.** Confirmations with outcome, who, when and after-photo map to AC 150/5220-24 §3.2.c(1) disposition records and -24A §6.1.1 fields. They can be kept per Part 5 §5.97 if Delta classes them as safety-assurance data (WF "silent" #1). This fits Delta's "a human is always present in the safety system" and Safety Time Out culture [P]. Vendors found alert, or auto-declare clear, without a named-role confirmation step.
4. **Honest INCOMPLETE.** A glare-blinded or blocked engine Angle blocks ALL CLEAR (FOD-R6). No vendor material found describes coverage-failure handling.
5. **Local-first, low marginal cost.** Change-detection proposer runs on CPU in 0.9 s per 4K frame. Hybrid cost is **$0.03–0.04 per 6-Angle Inspection**, about $0.008 if Haiku-only (RESULTS.md). At, say, 2 Inspections × 5 gates × 10 turns/day, that is roughly $3–4/day in API cost, **before** compute, cameras and integration. *Illustrative arithmetic, not a TCO.* The only public comparators are runway systems: BOS FODetect $1.7M; Trex about $400k or $12–15k/month [S].
6. **Matches Delta's stated wish.** "Spotting safety hazards on the ramp, such as oil spills or misplaced equipment" [P, Jun 2025]. FOD-R9 covers misplaced equipment. Spills would be a small extension to FOD-R7 observations.

### Gaps and risks (be explicit in the pitch)
1. **Snapshots, not continuous coverage.** Two scheduled Inspections plus on-demand. Anything dropped after the pre-departure capture is missed (WF #10, #11 "can't verify"). Vendors stream every 5 s (Deep Turnaround) or continuously (ADB).
2. **Evidence is synthetic.** 28 composited objects. Thresholds were tuned on the same set. The real-world Candidate rate from moving GSE, people and shadows is unmeasured (RESULTS.md caveats). Must be re-measured on staged captures (0011) before any accuracy claim.
3. **Latency.** About 12–17 s per Inspection vs 6–9 s for the Claude-only baseline. Acceptable only if a pre-push window allows it. No public Delta turn target exists to check against.
4. **Camera access at ATL is unknown.** The ATL cameras with AI overlays are the airport's and security-focused [P, ATL CIO 2026]. Whether Delta-controlled stand cameras at Concourse T exist, with the fixed angles every vendor needs, is for 0015. Change detection also needs fixed cameras and a Confirmed-clean reference.
5. **No people/SOP detection, no milestones, no VDGS/AODB/A-CDM integration.** Do not compete here. Offer a JSON feed (the report schema) for a turnaround platform or Delta's tower to consume.
6. **Cloud LLM dependency.** "Local-first" is true for proposing, not deciding. ATL chose on-prem for its CV overlays [P]. Delta's data-governance path (AI Governance Committee) would apply.
7. **No FAA standard for apron AI.** Benchmarks borrowed from AC 150/5220-24 (≤1 false alarm/day/90 days, 16 ft location) are runway equipment specs (`research/faa-fod-guidance.md`). The PoC is advisory and must say so.
8. **Responsibility split at ATL** for apron taxilanes is set by LOA and is not public (WF §5). FOD-R10 routing must stay configurable.
9. **Delta builds in-house** (Baggage AI). Expect the pitch to be judged as "a component Delta could own", not a vendor platform.

## 5. Recommended PoC scope and offer

### Scope for 0016
**In:**
- 5 Concourse T gates (from 0015) and 6 Angles each.
- `pre_arrival` and `pre_departure` Inspections plus `on_demand` re-inspection.
- FOD Findings (FOD-R1–R6, R8, R10), GSE-staging Findings (FOD-R9) and non-FOD observations (FOD-R7). Consider adding a `spill` observation kind, because Delta named it.
- Role-gated Confirmations and gate status by highest open severity.
- An exportable per-Inspection record (schema v0.1) with retention set per 0016.
- A cost and latency readout per Inspection.

**Out:**
- Turn milestones and OTP prediction.
- People, PPE and wing-walker detection.
- Continuous video monitoring.
- Engine or beacon state.
- VDGS, AODB or A-CDM integration (offer a JSON output only).
- Any automatic clearing.
- Movement-area FOD (the airport's runway systems).

### Offer statement
> **A gate-level FOD check on the cameras Delta already has.** Before each arrival and before each pushback, the system inspects six named zones at the stand: nose, both engine intakes, cargo, aft and wide. It flags each piece of debris or misplaced GSE with a photo crop, a severity (HOLD, REMOVE or ADVISORY) and the FAA or IGOM rule behind it. If it cannot see a zone, it says so instead of calling the stand clear. Nothing clears without a person: only the Ramp Lead can clear a HOLD, and every confirmation is kept as an audit record for Delta's SMS. It costs cents per inspection, proposes candidates locally, and feeds Delta's ramp tower or turnaround tools rather than replacing them.

### Demo moments (in a 5-gate dashboard, staged or composited frames)
1. **Bolt in the engine intake → HOLD.** Pre-departure Inspection at one gate. A 22 px bolt in ENG-L. The Finding shows the current crop next to the reference crop, `FOD-R1 · HOLD`, and its basis (-24A §2.2.1, §4.1.1.1). Gate tile turns red. This is the case Claude-only runs missed and the reference crop caught (RESULTS.md).
2. **Misplaced GSE before arrival → REMOVE.** A belt loader parked inside the equipment restraint line at pre-arrival. `FOD-R9 · REMOVE`, basis IGOM 4.1.1(d) and ATL C2.4. This answers Delta's "misplaced equipment" wish directly.
3. **Glare on the right engine → INCOMPLETE, not ALL CLEAR.** ENG-R unusable (glare). Verdict INCOMPLETE with `missing_angles: [ENG-R]`. The stand can't be cleared until it is re-shot. This shows the system won't pretend.
4. **Who can clear a HOLD.** A Ramp Agent tries to confirm the HOLD and is refused. The Ramp Lead confirms `removed` with an after-photo. An `on_demand` re-inspection returns ALL CLEAR. Then open the audit record: who, when, outcome, rule and Inspection IDs, mapped to AC 150/5220-24 §3.2.c(1) fields.
5. **Debris beyond the stand → routed, plus the bill.** An item on the taxilane seen only in WIDE is tagged `outside_boundary` and routed to ramp control / Airport Ops per FOD-R10. Close on the run metadata: local proposer time, model calls, **≈$0.03 for the Inspection**.

## Not covered / follow-ups
- Re-read the Delta 2025 10-K AI section on EDGAR to quote it directly.
- Ask Delta whether Concourse T has Delta-controlled fixed stand cameras, and their resolution and mount height. All camera-AI vendors need this (0015 / later).
- Confirm whether Southwest's ATL ApronAI trial is still live. If it is, ATL already has an apron-camera precedent and possibly camera infrastructure.
- Get ADB SAFEGATE and ArgosAI deployment lists and any accuracy data. Neither is public.
- Check the Part 139 Airport SMS rule's scope for non-movement areas (aprons) to see whether ATL's SMS would also take in gate FOD records.
