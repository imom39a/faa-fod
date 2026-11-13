---
id: 13
title: "Which internet image archives can supply an openly licensed gate/apron test set per Angle?"
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

Real airport data is only available after the PoC. Find internet sources of **real** photographs of narrowbody aircraft (A320 family / 737) parked at gates or on apron stands, usable for an internal PoC test set. For each source report: licence and terms (incl. API / bulk-download terms and whether ML evaluation use is allowed), how to query it, and estimated counts per Angle (NOSE, ENG-L, ENG-R, CARGO, AFT, WIDE), day/night/wet variety, and resolution. Candidates include Wikimedia Commons categories, Flickr CC-licensed search via its API, US-government public-domain imagery (FAA, NASA, DoD/DVIDS, NTSB), Openverse, airport media/press galleries, and public video frame extraction (check terms). Also check for any real apron images that already contain FOD or GSE clutter (valuable as natural false-alarm tests). Output a ranked source list plus a reproducible download manifest approach (query → licence filter → attribution record), and prototype the manifest with a small sample.

## Resolution

Findings: [research/gate-image-archives.md](../research/gate-image-archives.md). Manifest prototype: [prototypes/image-archive/](../prototypes/image-archive/) (117 sampled photos, hand-tagged).
- **Source ranking:** Wikimedia Commons first (no API key, machine-readable licences, no non-commercial licences). Flickr second (API key, storage restrictions). Openverse third. Airport press galleries are editorial-only and YouTube frames are barred by its terms.
- **Yield:** 42% of general results and 72% of gate-specific results were usable narrowbodies at a stand. About 22% night or dusk, 26% wet.
- **Angle coverage is lopsided:** of 23 usable images, WIDE 61%, NOSE 52%, CARGO 52%, ENG-R 26%, ENG-L 4%, AFT 0%. Projected internet set: 450–600 images, with about 20 ENG-L and 0–60 AFT. The sample is small, so these are rough.
- **ATL:** about 590 Delta-at-ATL files on Commons, but only 12% of those sampled were usable stand photos. Nothing identifiable as Concourse T.
- **Empty stands with staged GSE are rare** (3 of 55), so the pre-arrival set needs a targeted pass.
- **Licence conditions:** show attribution wherever an image is displayed; composites made from CC BY-SA photos stay BY-SA if shared; faces and Delta livery need a check before any external demo.
- **Open for the user:** a team contact URL or role mailbox in the User-Agent raises the Commons limit from 10 to 200 requests a minute for the bulk run.
