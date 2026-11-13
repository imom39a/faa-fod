# FOD Rule Set (PoC v0.2)

These are airline FOD program rules, derived from FAA guidance. FAA text is advisory and mostly addressed to the airport; these rules are the airline's own. Findings cite the rule ID, and the FAA basis is shown alongside.
Decided in issue 0006 ("What FOD rule set and severity-to-action mapping will the agent apply?").

## Severity levels
| Level | Meaning | Who can confirm |
|---|---|---|
| **HOLD** | Immediate hazard. No pushback, engine start or aircraft movement until a Confirmation records the item as removed. | Ramp Lead only |
| **REMOVE** | Must be removed before departure. Servicing continues, but the pre-departure Inspection can't be ALL CLEAR while it remains. | Ramp Agent or Ramp Lead |
| **ADVISORY** | Logged and picked up in normal cleaning. Blocks nothing. | Ramp Agent or Ramp Lead |

FAA basis: AC 150/5210-24A §4.1.1.1 (immediate hazard → supervisor may stop operations; otherwise remove when the schedule permits).

## Zone tiers
| Tier | Angles |
|---|---|
| Critical | ENG-L, ENG-R (engine intake zones), NOSE (pushback path, nose-gear tyres) |
| Service | CARGO, AFT |
| General | anything visible only in WIDE, inside the gate safety envelope |
| Outside boundary | outside the gate safety envelope (taxi lane, adjacent stand). Responsible party is the airport: notify Airport Ops |

## Categories
1. Fasteners & hardware *(hard)*
2. Aircraft parts *(hard)*
3. Tools *(hard)*
4. Luggage parts *(hard; bag tags count as light)*
5. Catering & flight-line items *(light; metal items such as cans or pens count as hard)*
6. Cargo & packaging *(light)*
7. Pavement & construction debris *(hard)*
8. Natural, i.e. dead wildlife and vegetation *(natural)*
9. Unidentified object *(unidentified)*

Seeded from AC -24A §2.2.3.1. There is no minimum size, per §2.2.3.1 ("any … size"). Size (S/M/L) is recorded but never used to drop a Finding.

## Severity matrix
| Object class | Critical | Service | General |
|---|---|---|---|
| Hard | HOLD | REMOVE | REMOVE |
| Light | HOLD | REMOVE | ADVISORY |
| Unidentified | HOLD | REMOVE | REMOVE |
| Natural | HOLD | REMOVE | ADVISORY |

## Rules
| ID | Rule | Severity | FAA basis |
|---|---|---|---|
| FOD-R1 | The engine intake zones (ENG-L, ENG-R) must be free of FOD. | HOLD | -24A §2.2.1 (ingestion), §4.1.1.1 |
| FOD-R2 | The pushback path and nose-gear area (NOSE) must be free of FOD. | HOLD | -24A §2.2.1 (tyre damage), §4.3.2.3.1 |
| FOD-R3 | The service zones (CARGO, AFT) must be cleared of FOD before departure. | REMOVE | -24A §3.3.1, §4.3.1.1.3; 14 CFR §139.305(a)(4) |
| FOD-R4 | FOD on the stand perimeter (WIDE only): hard or unidentified items must be removed; light or natural items are logged. | REMOVE / ADVISORY | -24A §4.1.1.1 |
| FOD-R5 | An object that can't be identified is treated as FOD at its zone's severity. | per zone | -24A §2.2.3.1 |
| FOD-R6 | Every required Angle must be usable. Otherwise the Verdict is INCOMPLETE and the Inspection can't be ALL CLEAR. | — | -24A §4.3.2.3.1 (inspect apron before movement) |
| FOD-R7 | Snow, ice, spills and live wildlife are reported as *non-FOD hazard observations* and kept out of the FOD Verdict. | — | -24A §2.2.3.2, §4.3.2.2.3 |
| FOD-R9 | At pre-arrival, GSE must be staged behind the equipment restraint line. GSE inside it is an equipment-staging Finding. | REMOVE | IATA IGOM 4.1.1 (GSE outside the equipment restraint area before arrival) |
| FOD-R10 | FOD outside the gate safety envelope is reported to ramp control and/or Airport Operations, according to the local agreement (responsible party: airport or ramp control). | per matrix (displayed) | -24A §3.3.1; ATL routing (research/atl-concourse-t-site.md): shared taxilane between stands → ramp control, for the airlines' contractor AATC (lease §12.01.B); movement area beyond the zipper marking → Airport Operations |
| FOD-R8 | GSE, chocks, cones and tow bars in their normal positions are not FOD. Loose or misplaced ones are FOD (Tools / Unidentified). | per matrix | -24A §2.2.2.1 (equipment as a FOD source) |

## Policies
- **Confidence never lowers severity.** It is displayed, and the person confirming dismisses false alarms.
- **Gate status shows the highest severity among unconfirmed Findings.** A HOLD shows even when the Verdict is INCOMPLETE. Which Verdict takes precedence is decided in the report schema ticket.
