# Glossary

**FOD (Foreign Object Debris)**: Any object at the gate or apron that doesn't belong there and could damage an aircraft or hurt someone (per FAA usage). In this project it means debris on the ground only, not defects on the aircraft itself.

**Gate**: One of the monitored aircraft parking positions. The PoC example covers 5 Gates.

**Turn**: One aircraft's visit to a Gate, from stand preparation (before the pre-arrival Inspection) to pushback.

**Inspection**: One analysis of a set of multi-angle images captured for a Turn. A Turn has a *pre-arrival* Inspection (stand empty, before the aircraft enters), a *pre-departure* Inspection (after the jet bridge retracts and GSE clears, before engine start), and may have extra *on-demand* Inspections.

**Finding**: One suspected FOD item that an Inspection identifies, with its location in the image, category, severity, and the rule it breaks.

**Candidate**: A region a local image model proposes as *possibly* debris. A Candidate becomes a Finding only once the reasoning step judges it FOD.

**Verdict**: The result of an Inspection: **ALL CLEAR**, **FINDINGS**, or **INCOMPLETE** (a required Angle was missing or unusable, so the Inspection can't clear the stand). It is advisory until a human confirms it.

**Angle**: A named view an Inspection must cover, defined by the ground zone it shows (e.g. ENG-L = the left engine intake zone), not by the physical camera. Each Gate maps its cameras to Angles.

**Zone**: An area of ground around the parked aircraft that an Angle is responsible for showing.

**Confirmation**: A ramp agent or supervisor accepts or overrides a Verdict or a single Finding (e.g. "removed", "false alarm"). Only a Confirmation clears a Gate.

**Severity**: How urgent a Finding is: **HOLD** (immediate hazard, no aircraft movement until removed), **REMOVE** (must be gone before departure), or **ADVISORY** (log it and clean it up as you go).

**Ramp Agent**: Ground staff who can confirm REMOVE and ADVISORY Findings.

**Ramp Lead**: The pushback lead / headset operator at the gate, who confirms to the flight crew that the area is clear (the flight crew clears engine start and pushback). The only role that can clear a HOLD.

**Gate safety envelope**: The painted boundary around a stand. FOD inside it is the airline's to remove; FOD outside it is not the ramp crew's to remove: it is reported to ramp control or Airport Operations, depending on where it lies and the local agreement.

**Equipment restraint line**: The painted line GSE must stay behind while an aircraft moves on or off the stand.
