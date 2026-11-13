# FAA FOD guidance: categories, severity, inspections, responses, records

Research for ticket 0002 (`issues/0002-faa-fod-guidance-extraction.md`). Retrieved 2026-11-13.

## Sources (primary, FAA / eCFR only)

| Short name | Document | URL |
|---|---|---|
| **FOD page** | FAA Foreign Object Debris Program page (last updated 2026-04-15) | https://www.faa.gov/airports/airport_safety/fod |
| **AC -24A** | AC 150/5210-24A, *Airport FOD Management*, 2/8/2024 (status: Active), consolidated PDF incl. errata of 5/20/2024 | https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC-150-5210-24A-FOD-Mgmt.pdf |
| **Errata** | Errata Sheet for AC 150/5210-24A (5/20/2024) | https://www.faa.gov/documentLibrary/media/Advisory_Circular/errata-sheet-150-5210-24a.pdf |
| **AC -18D** | AC 150/5200-18D, *Airport Safety Self-Inspection*, 9/27/2022 | https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_150_5200_18d_self_inspection_rev.pdf |
| **AC 5220-24** | AC 150/5220-24, *FOD Detection Equipment*, 9/30/2009 | https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_150_5220-24.pdf |
| **14 CFR 139** | §139.305 Paved areas; §139.327 Self-inspection program (eCFR, current) | https://www.ecfr.gov/current/title-14/part-139 |

**Version note (important for citations):** the ticket names AC 150/5210-24 (9/30/2010). That AC is **cancelled**; it was replaced by **AC 150/5210-24A** (AC -24A §2). The FAA AC index link for "150_5210-24" now resolves to -24A. The text is largely identical, but paragraph numbering changed (e.g. 2010 "4.1.b(1)" is now "4.1.1.1"). Content changes in -24A that matter here: §4.2 risk assessment now points to Part 139 Subpart E SMS and AC 150/5200-37A (Errata #1); §6.1.4 says the national FOD database now exists (FOD.FAA.GOV); §2.3.1.2 quotes -18D's stronger "must continuously check" wording. **The PoC should cite -24A section numbers.**

## Status of the guidance (what "rule" means here)

- AC -24A is advisory: "does not constitute a regulation, is not mandatory and is not legally binding" except for AIP/PFC-funded projects; it is "one, but not the only, acceptable means" of meeting Part 139 (AC -24A §4). Its guidelines "can be implemented at the discretion of the airport operator in accordance with the ... Airport Certification Manual" (§3).
- It is aimed at airport operators **and air carrier station managers** (§3), so an airline can adopt it for its gates.
- The binding layer is 14 CFR Part 139 (certificated airports only): §139.305(a)(4) and §139.327 (quoted below). These bind the airport certificate holder, not the airline directly. Tenant/air-carrier inspection of leased areas can be delegated via Letters of Agreement or leases, but the certificate holder stays accountable (AC -18D §3.3).
- Implication for the PoC: Findings can cite FAA text, but the "rule broken" will mostly be *FAA-recommended practice* or *the airline's own program rule derived from it*, not a regulation. Only §139.305(a)(4) is a hard "must remove" rule, and it addresses the airport operator.

## 1. Definitions

- **FOD**: "Any object, live or not, located in an inappropriate location in the airport environment that has the capacity to injure airport or air carrier personnel and damage aircraft." (AC -24A §1.1 item 4; repeated verbatim on the FOD page.) ICAO definition will take precedence if adopted (same note).
- **FOD Damage** is defined separately; in the AC "FOD" means debris only (§1.1 item 5). This matches GLOSSARY's "debris on the ground only".
- **Airport Apron (or Ramp)**: "A surface in the AOA where aircraft park and are serviced (refueled, loaded with cargo, and/or boarded by passengers)." (§1.1 item 2.)
- **Hazard**: "A condition, object or activity with the potential for causing damage, loss, or injury." (§1.1 item 6.)
- **Clean-as-you-go**: cleaning surroundings before, during and after a shift (§1.1 item 3).
- AC 5220-24 §1.1 adds detection-system terms: **Alert** (item d), **False Alarm** = "an alert causing the airport operator to take action to remove a FOD object that does not exist" (item h), **Image Processing** (item l).

## 2. Categories

The AC gives two non-exclusive groupings, neither presented as a formal classification scheme.

### 2a. By source (AC -24A §2.2.2.1)
FOD "can be generated from":
1. **personnel**
2. **airport infrastructure** (pavements, lights, signs)
3. **the environment** (wildlife, snow, ice)
4. **equipment operating on the airfield** (aircraft, airport operations vehicles, maintenance equipment, fueling trucks, other aircraft servicing equipment, construction equipment)

Additional source/movement notes: FOD collects on and below GSE staged on the apron and jet blast can blow it onto personnel or aircraft (§2.2.2.2); helicopter rotor wash (§2.2.2.3); construction and winter pavement break-up (§2.2.2.4); wind and rain move debris (§2.2.2.6).

### 2b. By type ("FOD Taxonomy", AC -24A §2.2.3.1)
"FOD can be composed of any material and can be of any color and size." Cited study: >60% metal, 18% rubber, ~50% dark-coloured. "Typical FOD includes":
1. aircraft and engine fasteners (nuts, bolts, washers, safety wire)
2. aircraft parts (fuel caps, landing gear fragments, oil sticks, metal sheets, trapdoors, tire fragments)
3. mechanics' tools
4. catering supplies
5. flight line items (nails, personnel badges, pens, pencils, luggage tags, soda cans)
6. apron items (paper and plastic debris from catering and freight pallets, luggage parts, debris from ramp equipment)
7. runway and taxiway materials (concrete/asphalt chunks, rubber joint materials, paint chips)
8. construction debris (wood, stones, fasteners, misc. metal)
9. plastic and/or polyethylene materials
10. natural materials (plant fragments, wildlife, volcanic ash)
11. contaminants from winter conditions (snow, ice)

Caveats: snow/ice is handled under AC 150/5200-30, not by FOD removal (§2.2.3.2; §139.305(b) also excludes snow/ice from (a)(4)). **Dead wildlife** goes in the FOD program; **live wildlife** goes in the wildlife hazard program (§4.3.2.2.3).

### 2c. Gate/apron hotspots named by the AC
- "Anywhere on the aircraft apron where ground vehicles operate" (§4.3.1.1.2).
- Aircraft servicing (refuelling, catering, cabin cleaning, baggage/cargo) "can produce broken materials"; bag tags and wheels break off luggage onto the apron or into the aircraft door sill; FOD collects "at both ends of the conveyor, and the area between the baggage cart and the conveyor belt" (§4.3.1.1.3).
- Air carriers and tenants "generate much of the FOD found in the airport apron"; luggage items (baggage wheels, zippers, accessories) are common apron FOD (§3.3.1).
- Apron maintenance leaves rivets, safety wire, bolts; tools should be accounted for (§4.3.1.1.6, §3.3.2).
- Cargo areas: strapping, plastic wrappers (§3.3.3, §4.3.1.1.4).
- Broken pavement collects at the apron edge and GSE tyres carry it onto manoeuvring areas (§4.3.1.1.1 item 2).

The size/material reference objects in the equipment specs (AC -24A §5.3.2.1; AC 5220-24 §3.2.b(1)) are useful as **test objects** for the PoC: metal cylinder 1.2 in × 1.5 in dia; 1.7 in sphere (golf ball); asphalt/concrete chunk; light-fixture piece; wrench ≤8 in; socket ≥2 in; tyre rubber; distorted metal strip ≤8 in; fuel cap; lug nut; hydraulic line ≤8 in; aircraft fasteners and safety wire (-24A); white 2 in PVC pipe (5220-24). They are equipment acceptance objects, not a severity or minimum-size rule.

## 3. Severity / risk classification

**The FAA defines no severity scale, size threshold or category-to-severity mapping.** What it does say:

- **Binary "immediate hazard" test** (AC -24A §4.1.1.1): "If the location or characteristics of the FOD present no immediate safety hazard the object should be removed as soon as the operational schedule permits. If the location or characteristics of the FOD present an immediate safety hazard, provisions in the FOD management program should clearly indicate that a hazard exists and allow for an airport supervisor to take action and temporarily cease operations and, in the case of aircraft or airport equipment source of the FOD, notify the equipment operator." Deciding what counts is left to the airport, e.g. "an appropriate issue ... for an airport's FOD committee to study" (same para). The deciding factors are **location** and **characteristics**.
- "Quick and decisive action should be taken, in all cases, to assess the threat posed by reported FOD", even though not all FOD needs a runway closure (§4.1.1.2, citing CertAlert 09-06; runway-focused).
- The FOD committee may make "the determination of potentially hazardous FOD situations" (§3.1.2.3.3).
- Risk assessment is handed to the SMS: for Part 139 Subpart E airports, it sits in the SMS Safety Risk Management; AC 150/5200-37A process is "a good practice for all airports" (§4.2 as amended by Errata #1). The AC gives no FOD-specific matrix.
- Documentation tiers hint at severity: small items like plastic wrappers or baggage tags "may simply warrant efficient collection and disposal"; "particularly large or hazardous FOD" or a consistent trend from one source "may require detailed documentation" (§6.1.1). "Major FOD incidents" are "as determined or classified by the airport operator" (§6.1.3).
- Detection systems: an alert "must provide airport management with enough information to assess the severity of the hazard in order to determine if immediate object removal is necessary" (AC 5220-24 §3.2.b(7)). So severity is the operator's assessment, and the system must supply the inputs.
- Surveillance-area priority for detection equipment: runway first, "decreasing level of priority from other paved movement areas down to non-paved, non-movement areas" (AC 5220-24 §3.2.b(5)). Aprons are generally non-movement areas, so they are **lower priority** in that scheme.
- Contextual risk cues: the take-off portion of the runway is where departing aircraft are most susceptible (§4.3.1.1.1 item 1); jet blast can propel FOD at high velocity and injure or kill personnel (§2.2.1); damage modes are tyre cuts, engine ingestion, lodging in mechanisms (§2.2.1).

## 4. Inspection practices (frequency, FOD walks, timing vs pushback)

- **Regulatory frequency (certificated airports):** inspect "Daily, except as otherwise required by the Airport Certification Manual"; when unusual conditions such as construction or weather require it; and "Immediately after an accident or incident" (14 CFR §139.327(a)(1)–(3)).
- AC -24A §4.3.2.1: "The FAA and ICAO require a daily, daylight inspection of aircraft operating areas"; extra inspections in construction areas and right after any aircraft/ground-vehicle accident, incident or slippery spill; plus **clean-as-you-go** looking for FOD during normal shifts. Night inspections need extra lighting.
- AC -18D §7.2.7 (continuous surveillance): "The inspector must continuously check for and remove any debris in movement areas, non-movement areas, **aircraft parking areas, and loading ramps**." This is the most direct FAA statement covering gates. AC -18D §4.1.1: larger airports normally inspect several times a day, with the first before the first air-carrier operation; §4.1.2 continuous surveillance; §4.1.3 special inspections after complaints or unusual events.
- **Gate timing, the only pushback-related text:** "Air carrier and aircraft handling agents may also be asked to designate individuals to **inspect apron areas prior to aircraft movement to and from the gate**." (AC -24A §4.3.2.3.1.) This supports the PoC's *arrival* and *pre-departure* Inspections. The wording is permissive ("may be asked"), not a requirement.
- **Per-turn baggage area check:** "Procedures to inspect the baggage loading and unloading areas **every time an aircraft is serviced** can also be helpful" (§3.3.1).
- Air carrier staff "should join the airport staff in daily movement area inspections" when feasible (§4.3.2.3.3).
- **FOD walks** are all-hands campaign events (ground handlers, air carriers, ARFF, apron staff, volunteers) to collect FOD by hand. They are described as a good practice, with no frequency given. The AC notes that location and origin often cannot be recorded during walks (§4.3.2.3.3 item 1).
- **Automated detection:** if used, "personnel monitoring these systems either have the authority (or the ability to quickly contact those in authority) to take appropriate and timely action" (§4.3.2.2.1). Airports and air carriers have "considerable flexibility" in where alerts go and how removal crews and ATC are notified (§4.3.2.2.2). Equipment specs are in AC 5220-24 (§4.4). AC 5220-24 inspection frequency for mobile/continuous systems is "specified by the user" (§3.2.b(3)). The response-time default is within 4 minutes for continuous systems (§3.2.b(4)(b)). False alarms must not exceed 1/day averaged over 90 days for systems with visual detection (§3.2.b(7)(a)). Location accuracy is within 16 ft (§3.2.b(2)). These figures are runway-oriented specs for procured equipment; the PoC can borrow them as benchmarks, not obligations.

## 5. Required responses

- **Remove:** §139.305(a)(4): "mud, dirt, sand, loose aggregate, debris, foreign objects, rubber deposits, and other contaminants must be removed promptly and as completely as practicable". It applies to each "runway, taxiway, **loading ramp, and parking area** ... available for air carrier use" (§139.305(a)). This is binding on certificated airport holders. No time limit is defined beyond "promptly".
- **Non-immediate hazard:** remove "as soon as the operational schedule permits" (AC -24A §4.1.1.1).
- **Immediate hazard:** the program should let an **airport supervisor** "temporarily cease operations" and notify the equipment operator if aircraft or airport equipment was the source (§4.1.1.1). Through the detection-notification chain, notify personnel to remove the FOD and ATC "to divert aircraft if a significant risk is presented" (§4.3.2.2.2).
- **Personnel:** all personnel should be "actively encouraged to identify potential FOD hazards, act to remove observed FOD, and propose solutions" (§3.1.1). Training includes "How to report FOD incidents or potential incidents" (§3.2.3 item 11).
- **Removal method:** an isolated object is most efficiently removed by hand (§5.1). Put debris in closed, secured, marked FOD containers, "conspicuously placed **at all gates**" and at each gate/baggage area (§5.2.3.1–5.2.3.3). Do not rely on equipment alone; visually confirm pickup (§5.4.3).
- **Report / notify source:** have a well-defined reporting procedure and a visible reporting system (§6.1.2.1–6.1.2.2). The program "may contain provisions to notify the FOD source" (§6.1.2.3).
- **Investigate:** major FOD incidents (operator-classified) should be investigated for source and damage; corrective action and final disposition go into the FOD reporting system (§6.1.3; App. A items 4, 5, 8).
- **NOTAM:** the airport operator must issue a NOTAM for deficient conditions with "immediate and critical impact on the safety of aircraft operations" (AC -18D §5.2.2). This is an airport, not airline, action and is unlikely to apply to gate FOD.
- Part 139 also requires "A reporting system to ensure prompt correction of unsafe airport conditions noted during the inspection" (§139.327(b)(4)).

## 6. Record-keeping

- **Per-item FOD record** (AC -24A §6.1.1), "to the extent practicable, whenever FOD is collected":
  1. How the FOD object was detected
  2. Date and time of FOD detection and retrieval
  3. Description of FOD retrieved (category, size, color), and/or **image (if available)**
  4. Location of FOD object (coordinates and reference to the AOA location)
  5. Possible source
  6. Name of personnel detecting / investigating FOD item
  7. Airport operations and weather data during the FOD detection event

  The FOD manager "will ultimately determine the documentation guidelines" (§6.1.1).
- **Retention:** "All records should be maintained in sufficient detail for a period of **at least 2 years** to ensure traceability of all significant safety-related decisions" (§6.1.4). Records support §139.327 certification and may be needed in accident investigations. National FOD database: submit type/location/source data at FOD.FAA.GOV (§6.1.4).
- **Regulatory inspection records (certificated airports):** each self-inspection record shows "the conditions found and all corrective actions taken", kept ≥12 consecutive calendar months (§139.327(c)(1)). Training records are kept 24 months (§139.327(c)(2)). Electronic logs are acceptable if they can be printed or produced for the FAA (AC -18D §5.2, §5.2.1). A work-order system is needed to track corrections (§5.1).
- **Detection-system records** (AC 5220-24 §3.2.c(1)): *required* are alert time/date and location. *Recommended* are description, retrieval time/date, **disposition time/date of the alert**, investigating personnel, image, and chain of custody. This maps closely to a Finding plus Confirmation record.
- **Training records:** a file per employee (AC -24A §3.2.4).
- FOD manager to ensure written procedures provide adequate records (App. A item 11).

## 7. Where FAA guidance is silent (the airline/PoC must decide)

1. **Severity scale.** No levels, no size/material/location thresholds, no category-to-severity mapping. Only "immediate safety hazard vs not" (§4.1.1.1), with the airport/FOD committee deciding. The PoC must define its own severity levels and justify them, e.g. by damage mode (§2.2.1), location relative to engine inlets/tyre paths, and jet-blast exposure.
2. **Minimum detectable/relevant size.** None. "Any material ... any color and size" (§2.2.3.1). The equipment test objects (~1.2–1.7 in) are acceptance tests, not a reporting threshold.
3. **Gate-specific timing.** No mandated inspection before block-in or pushback. §4.3.2.3.1 only says handling agents "may be asked" to inspect before movement to and from the gate. Inspection cadence per Turn, and whether a Finding blocks pushback, are airline decisions.
4. **Who may stop operations at a gate.** The AC gives the stop authority to an "airport supervisor" (§4.1.1.1). It is silent on airline ramp agents or supervisors halting a pushback or arrival. Airline SOPs and the airport's ACM/LOAs must define this, which feeds the Confirmation role.
5. **Removal deadline.** Only "promptly" (§139.305(a)(4)) and "as soon as the operational schedule permits" (§4.1.1.1). There is no time number.
6. **AI/camera-based detection.** Neither AC addresses gate cameras, still-image analysis, or ML classifiers. AC 5220-24 (2009) targets runway radar/EO systems. Its false-alarm limit (≤1/day/90 days for visual systems), 16 ft location accuracy and record fields are the closest benchmarks, but they are not written for aprons. No FAA guidance on confidence thresholds, advisory vs authoritative outputs, or human-in-the-loop sign-off (beyond §4.3.2.2.1's requirement that monitors have, or can quickly reach, authority to act).
7. **Category taxonomy for reporting.** §6.1.1 asks for "category" but defines no category codes. The §2.2.3.1 list (11 types) and §2.2.2.1 sources (4) are illustrative. The PoC must fix its own enumerations; it can seed them from these lists.
8. **Airline vs airport responsibility split.** Set by leases and LOAs (AC -18D §3.3) and by carrier/support-org agreements on "which of the parties are responsible for cleaning various areas" (AC -24A §3.3.1). The FAA does not prescribe it.
9. **Retention for airline records.** The 2-year figure (§6.1.4) is a recommendation addressed to the FOD program. The 12-month figure (§139.327(c)) binds the airport certificate holder only. The airline must pick its own retention, and ≥2 years is the FAA-aligned choice.
10. **Risk-assessment method.** The AC defers to SMS and AC 150/5200-37A (§4.2, Errata #1). Not reviewed here; follow-up if a FOD risk matrix is needed.

## Not covered / follow-ups

- AC 150/5200-37A (SMS risk assessment) and CertAlert 09-06 were not read; they are cited only through AC -24A.
- The ACRP Synthesis 26 and Tech Center FOD characterization papers linked from the FOD page were not read: ACRP is not FAA-authored, and the Tech Center papers are research, not guidance. The characterization paper could inform a frequency-of-category prior for test data (ticket 0004).
- ICAO Annex 14 §10.2.1 is quoted in AC -24A §2.3.1.3 but was not checked against ICAO's text.
