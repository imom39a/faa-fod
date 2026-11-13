# PROTOTYPE: Gate dashboard (ticket 0009)

Throwaway, clickable mock for [issues/0009-gate-dashboard-ux.md](../../issues/0009-gate-dashboard-ux.md). It is evidence for a decision, not the build.

**Run:** open `index.html` in a browser (double-click; it also works over any static server). No backend. Inspection data is mock and in memory, so a reload resets it. **The camera frames are real photographs** (see "Real camera frames" below).

**Floating bar (bottom):**
- `←` / `→` (or the arrow keys) switch the Gate overview variant. The choice is kept in `?variant=A|B|C`.
- **Seed 1 / Seed 2** load two mock scenarios. Between them every Gate status appears:
  - Seed 1: idle, aircraft on stand, inspecting, ALL CLEAR, FINDINGS, INCOMPLETE.
  - Seed 2: confirmed clear, ALL CLEAR, awaiting Confirmation, FINDINGS with HOLD, idle, inspecting.
- **State** shows each Gate's derived status, the current view and an event log.

## What's in it

1. **Gate overview** in three variants that differ in structure:
   - **A, Tiles:** a 2×3 grid with one card per Gate. Each card shows the status chip, flight and STD countdown, a 6-Angle strip and a contextual next action.
   - **B, Apron map:** a spatial schematic of the 6 stands along the terminal, plus a "Needs a human" queue sorted by urgency.
   - **C, Triage list:** a table sorted by urgency (open HOLD first, then INCOMPLETE, awaiting Confirmation, unconfirmed ALL CLEAR, then time to STD), with inline actions.
2. **Turn drill-in:** a timeline running Block-in → arrival Inspection → on-demand Inspections → pre-departure Inspection → Pushback. It lists the Confirmation events (who, when, which action). An earlier Inspection that a later one replaced shows as "Superseded".
3. **6-Angle viewer:** a large real camera frame for the selected Angle plus a 3×2 grid of thumbnails, each with an OK / count / GLARE / BLOCKED badge. Findings are drawn as boxes in the severity colour and numbered, from pixel ground truth, so they sit on the actual debris at any display size. Hovering a box highlights its list entry and the reverse, and clicking either one selects it.
4. **Confirmation flow:**
   - Each Finding can be marked **Confirm & removed**, **False alarm** (pick a reason) or **Re-inspect <Angle>**. The last one starts an on-demand Inspection of that Angle only.
   - Each Inspection is then signed off with **Confirm Inspection & clear Gate**, or **Confirm ALL CLEAR** when nothing was found.
   - The **role switcher** in the header switches between R. Ortiz (Ramp Agent) and K. Bauer (Ramp Lead). Per spec/fod-rules.md only a Ramp Lead can clear a HOLD: for a Ramp Agent, "Confirm & removed", "False alarm" and "Undo" on a HOLD Finding are disabled, with a note. Re-inspect stays open to both roles.

## Design choices I made (react to these)

- **Gate status is derived from the latest Inspection of the current Turn**, never stored. The order is: no Turn → idle; no Inspection → aircraft on stand; running → inspecting; confirmed → confirmed clear; then the Verdict. A FINDINGS Verdict whose Findings have all been actioned becomes **Awaiting Confirmation**.
- **Two Confirmation levels.** Every Finding needs its own Confirmation before the Inspection-level sign-off is enabled. Only the Inspection-level sign-off clears the Gate.
- **"Advisory" is shown visually.** Statuses that come straight from Claude (ALL CLEAR, FINDINGS, INCOMPLETE) carry an "advisory" tag, and an unconfirmed ALL CLEAR has a dashed outline. Only a human-confirmed Gate gets the solid green "Confirmed clear" fill.
- **INCOMPLETE cannot be cleared.** The only way forward is **Re-inspect <failed Angles>**. That runs an on-demand Inspection of just those Angles and inherits the other Angles and their Findings and Confirmations. The "Clear Gate" button is shown disabled so the rule is visible.
- **Re-inspect on a Finding** also starts an on-demand Inspection of that one Angle. In the mock, a Finding with confidence below 60% disappears on re-inspection and a more confident one is found again, so both outcomes can be seen.
- **False alarm requires a reason**, picked with one tap from a short list. This is cheap for the agent and gives evaluation data back.
- **Severities and rules are the decided ones** from spec/fod-rules.md (issue 0006): HOLD (red), REMOVE (amber), ADVISORY (blue outline), and rules FOD-R1…R8 with their FAA basis. Each Finding shows its zone tier (Critical / Service / General) and cites one or more rules (an unidentified object cites its zone rule plus FOD-R5). Severity follows the matrix, so a 39–45% "possible debris" in an engine zone is still HOLD ("confidence never lowers severity").
- **A HOLD shows on the Gate chip even when the Verdict is INCOMPLETE** (spec policy), and open HOLDs sort to the top of the urgency order.
- **Each Finding card shows:** number, label, Angle, category, severity, confidence bar and cited rule. The list is sorted with open Findings first, then by severity.
- **The demo controls are explicit buttons:** "Block-in (demo)", "Finish now (demo)" and "Record pushback". Inspections a user starts finish on their own after about 3 seconds.

## Open UX questions for the human

1. **Which overview layout: A (tiles), B (apron map + queue) or C (triage list)?** Or a mix, such as B's "Needs a human" queue next to A's tiles?
2. **Should "Awaiting Confirmation" be its own Gate status, and does an unconfirmed ALL CLEAR count as awaiting Confirmation?** Right now ALL CLEAR (unconfirmed) and "Awaiting Confirmation" (all Findings actioned, sign-off pending) look different. You could argue they are the same thing to a ramp agent: "a human needs to tap Confirm".
3. **Is per-Finding plus per-Inspection Confirmation too many taps at a 35-minute turn?** Alternatives: a bulk "all removed" action, or letting the last Finding's Confirmation clear the Gate automatically. Should "Confirm ALL CLEAR" require the agent to open all 6 Angles first?
4. **Should "Confirm" and "Removed" be two steps?** For example, "confirmed real, crew dispatched" now and "removed" later, so a HOLD item is tracked while someone walks out to it. Should removal need a fresh image as proof?
5. **Who can confirm what?** Decided: only a Ramp Lead clears a HOLD (now enforced). Still open: should a Ramp Lead be able to override INCOMPLETE (camera down, visual walk-around done)? The button is shown disabled, citing FOD-R6.
6. **How should urgency be ordered?** A HOLD at a Gate 30 minutes before STD versus an unconfirmed ALL CLEAR 8 minutes before STD: which one should be on top? Should the STD countdown, or alerts, drive the order?

## Real camera frames (replaces the SVG drawings)

The drawn aprons are gone. Every Angle frame is a crop of a real, openly licensed Wikimedia Commons photo, resized to 1600×900. Issue 0005 allows "an Angle may be a crop of a larger frame", so each Gate's 6 Angles come from a few high-resolution (5.8–6k px) photos of one aircraft on one stand. Full per-file sources, crops, authors and licences are in `assets/ATTRIBUTION.md`, and each frame shows a credit line.

| Set | Gates | Aircraft / stand | Coherence |
|---|---|---|---|
| **PEL** | G1, G4 | Pelita Air A320 PK-PWL, Jakarta CGK T3 stand 64. 3 photos, all **CC0** | Very high: same aircraft, same stand (the "64" stand marking is visible), 3 shots within 2 minutes from the terminal: front-left (NOSE, ENG-L, WIDE) and front-right (ENG-R, CARGO, AFT). |
| **THA** | G5, G6 | Thai A320 HS-TXS, Denpasar DPS. 3 photos taken 3 seconds apart, CC BY-SA 4.0 | Very high: same aircraft and moment. A tight shot covers NOSE, ENG-L and CARGO; a wide shot covers ENG-R, AFT and WIDE. WIDE is only slightly raised. |
| **GAR** | G2, G3 | Garuda 737-800 PK-GFV, CGK T3 (CC BY-SA 4.0), plus a Ryanair 737-800 port engine at Palma (CC BY-SA 3.0) for ENG-L | High for 5 Angles (one elevated right-side photo). **ENG-L is a fallback:** every T3 737 shot is taken from the right side, with the jet bridge hiding the left engine, so ENG-L is a different 737-800 (apron-level close-up, EI-DLY). |

**Debris** is real photographed debris from FOD-A (MIT): a bolt, nut, metal strap, luggage tag, pliers, box cutter, plastic sheet and rock fragments. It is pasted with the spike's feathered-mask, contact-shadow and brightness-match compositing at known positions. Each Finding box is the tight box of the pixels that changed (plus 5 px padding), stored in image pixels in `assets/scenes.json`. The page loads the same data from `assets/scenes.js`, so it works from file:// without fetch. Boxes are drawn in an SVG overlay whose viewBox is the image's own 1600×900 grid, so they scale exactly with the displayed image (measured centre error: 0 px at both the 808 px viewer and the 261 px thumbnails). Small boxes are padded to a minimum visible size.

**Low-confidence Findings are real marks in the photos, not pasted objects:** an oil stain (G3 ENG-R, false alarm "Shadow / stain"), a wet-pavement reflection (G5 WIDE) and a wash-water patch (G1 ENG-L). That is why they disappear on re-inspection, while pasted debris (confidence ≥ 60%) is found again.

**INCOMPLETE (Seed 1, G6):**
- **ENG-R BLOCKED** is a genuine obstruction. It is the second Thai photo, taken 1 s later from the same spot and registered to the first, with the JAS belt-loader truck driving into the right-engine ground zone.
- **CARGO GLARE** is a synthetic low-sun veiling glare and flare over the real frame.
- **Re-inspect ENG-R + CARGO** brings back the clean captures. AFT (with the pavement fragments) and WIDE are inherited from the same second capture.

**Rebuild:** `../spike/.venv/bin/python -I tools/fetch_sources.py assets/raw/orig` (re-downloads the about 60 MB of originals, which are not kept in the folder), then `../spike/.venv/bin/python -I tools/build_assets.py assets/raw/orig ../spike/data/raw/foda assets`. Placements are in `tools/composites.json`. `assets/` is about 6 MB (32 JPEGs).

**Caveats:**
- Two Gates share each stand set.
- The cameras are spotter photos from terminal windows, not fixed CCTV mounts.
- Pasted debris has crisper edges than real debris.
- The Garuda ENG-R frame has a small real blue item (a glove?) near the belt loader that is deliberately not labelled.
