# Internet gate/apron image archives: openly licensed test photos per Angle

Answers [issue 0013](../issues/0013-internet-gate-image-archives.md): which internet archives can supply **real**, openly licensed photos of narrowbody aircraft at gates or apron stands for the PoC test set before real gate-camera data exists, on what terms, and how many per Angle (NOSE, ENG-L, ENG-R, CARGO, AFT, WIDE; see [issue 0005](../issues/0005-camera-angle-set-per-gate.md)). It includes the coordinator's scope update: Delta at ATL Concourse T as the example deployment, A220 and 757 added to the narrowbody list, and empty stands with staged GSE counted as useful (pre-arrival Inspection).

Researched 2026-11-13. Each claim links to the source it came from. Counts marked *measured* come from the prototype in [`prototypes/image-archive/`](../prototypes/image-archive/). Datasets already covered in [fod-test-data-sources.md](fod-test-data-sources.md) (FOD-A, the AIT Apron Dataset and others) are not repeated here. This is not legal advice.

## Bottom line

- **Wikimedia Commons is the best source by a wide margin.** It needs no API key. Every file carries a machine-readable licence. Commons accepts only licences that allow commercial use, so no NC or ND licences are hosted. Gate- and apron-specific searches return about 1,000 candidate files. In my sample, **42% of all downloaded images (23/55) and 72% from gate-specific queries (13/18)** were usable narrowbody-at-stand photos.
- **The photos come from passengers and spotters, not cameras mounted around the stand.** Most are raised views from terminal windows. They cover **WIDE, NOSE and CARGO well, ENG-R partly, and ENG-L and AFT almost never** (1 of 23 and 0 of 23). A nose-in aircraft's left side faces the jet bridge and terminal, and the area behind the tail is far from any public viewpoint. Those two Angles must come from staged capture (0011) or synthetic views.
- **ATL Concourse T is essentially absent.** Commons has about 590 Delta-at-ATL files of the in-scope types, but a seeded random sample of 43 gave only **5 usable stand photos (12%)**. None is identifiable as Concourse T, and Commons has no Concourse T category. Openverse gave **0 of 18**: all were taxiway spotter shots. Concourse T imagery needs a permission-based source, either ATL or Delta media, or the PoC's own capture.
- **Projected achievable internet test set: about 450–600 usable images.** By Angle: roughly 300 WIDE, 260 NOSE, 260 CARGO, 130 ENG-R (mostly crops), about 20 ENG-L, and 0 to about 60 AFT. About 20% are night or dusk and about 25% wet. Detail is in §4. This is a good false-alarm and clutter set and a reasonable NOSE/CARGO/WIDE demo set. It cannot stand in for per-Gate camera geometry.
- **Licences are fine for internal evaluation, but three obligations follow:**
  1. Show attribution wherever an image is displayed, for example in the dashboard.
  2. Edited images (seeded-FOD composites) built from a **CC BY-SA** photo must stay BY-SA if they are shared.
  3. Identifiable ramp workers and airline liveries carry rights that the copyright licence does not cover.

## 1. Ranked sources

Each source is ranked on usable volume × licence clarity × Angle coverage. "Yield" means the share of downloaded images that were a usable narrowbody at a stand (not poor quality, near-duplicates removed).

| Rank | Source | Usable volume | Licence clarity | Angle coverage | Access | Measured yield |
|---|---|---|---|---|---|---|
| **1** | **Wikimedia Commons** (Action API, search + category walk) | High. Gate/apron search hits: "737 gate" 474, "A320 gate" 214, "737 apron" 233, "A320 apron" 104. GSE categories: Aircraft tugs 98, Ground power units 78, Jet bridges 61, Pushback tractors 45, Baggage handling 38. Aircraft at night 220 *(measured, totalhits / categoryinfo)* | **High.** Every file has `LicenseShortName` and `LicenseUrl` in `extmetadata`. "Commercial use of the work must be allowed"; "Media licensed exclusively under non-commercial only licenses (like CC BY-NC-SA) are not accepted" ([Commons:Licensing](https://commons.wikimedia.org/wiki/Commons:Licensing)) | NOSE, CARGO, WIDE good; ENG-R partial; ENG-L and AFT rare | No key. **10 req/min** for clients without contact info in the User-Agent; 200 req/min with a compliant UA ([Rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)) | General: **21/48**. ATL: **5/43** |
| 2 | **Flickr** (own API, licence filter) | Very high raw volume: Openverse alone indexes 536,219,600 Flickr images ([Openverse stats](https://api.openverse.org/v1/images/stats/)). Most aviation shots are spotter taxi or flight photos. Many good Commons files are Flickr imports | **Medium-high.** Licence IDs are explicit. Allow 4 (BY 2.0), 5 (BY-SA 2.0), 7 (No known copyright restrictions), 8 (US Gov work), 9 (CC0), 10 (PDM), 11 (BY 4.0), 12 (BY-SA 4.0). Reject 0–3, 6 and 13–16 (all rights reserved, NC or ND) ([licenses.getInfo](https://www.flickr.com/services/api/flickr.photos.licenses.getInfo.html)). The API terms add constraints (§2) | Similar to Commons. Geo search (`bbox`, or `lat`/`lon` with `radius` under 32 km) could target an airport, but needs a "limiting agent" such as a tag or minimum date ([photos.search](https://www.flickr.com/services/api/flickr.photos.search.html)) | **`api_key` required**. At most 500 per page and "at most the first 4,000 results for any given search query" ([photos.search](https://www.flickr.com/services/api/flickr.photos.search.html)) | Not run (keys excluded by brief) |
| 3 | **Openverse** (aggregator of Flickr, Commons and others) | Large index, but anonymous pagination is "limited, accommodating only the typical usage on openverse.org" ([API docs, auth](https://api.openverse.org/v1/)). Title and tag matching misses many relevant photos | **Medium.** `license_type=commercial,modification` filter. But Openverse "does not verify its licensing status" and users must verify independently ([Openverse ToS §3](https://docs.openverse.org/terms_of_service.html)) | Same as Flickr | No key. ToS: "You must not scrape the content in the Openverse catalog" ([ToS §2](https://docs.openverse.org/terms_of_service.html)). The image search returned **HTTP 504** for about 15 minutes during this run | General: **2/7**. ATL: **0/18** |
| 4 | **US-government public domain** (DVIDS, NASA, US Navy / USAF, mostly reachable through Commons) | Few civil narrowbodies at gates. But Commons "Foreign object damage" (47 files plus subcats such as *FOD walks*) holds dozens of public-domain military flight-line FOD-walk and intake-inspection photos *(measured)* | **High** with conditions. DVIDS works "are not eligible for copyright protection in the United States". They must not imply endorsement, should carry the non-endorsement disclaimer, and military markings should be obscured for commercial use ([DVIDS copyright](https://www.dvidshub.net/about/copyright)). NASA content is "generally … not subject to copyright", but commercial use must not imply endorsement and identifiable people need permission ([NASA guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)). Not everything on a federal website is a government work ([USA.gov](https://www.usa.gov/government-copyright)) | Almost none for gate Angles. Valuable as **real debris exemplars** | DVIDS search page and API not exercised. NASA hits in the sample were 1940s photos (rejected by eye) | General: 0/3 (NASA GRC) |
| 5 | **Airport / airline press galleries** | Small but on-target (current GSE, real stands) | **Low for this use.** Example: Munich allows editorial use with a credit line; "Use of these pictures for non-editorial or advertising purposes is possible only with written permission" ([Munich media center](https://www.munich-airport.com/media-center-264718)). Galleries generally split editorial from commercial use and differ per airport | Possibly the only route to **ATL Concourse T**, via a written request to ATL or Delta | Manual; permission per gallery | Not run |
| 6 | **Public video frame extraction** (YouTube) | High | **Not usable without permission.** The YouTube terms bar users from accessing, reproducing or downloading content without permission, and from "using any automated means (such as robots, botnets or scrapers)" ([YouTube ToS](https://www.youtube.com/static?template=terms)) | Would add ENG/AFT views from ramp-cam livestreams | Excluded. CC-licensed video on Commons is a legitimate alternative (not measured) | — |

## 2. Licence and terms notes

- **ML evaluation use.** Creative Commons says its licences "apply to reuse in any situation that requires permission under copyright law" and "have no effect on situations that do not require permission". The BY (attribution) and SA (ShareAlike) conditions are "triggered only upon public sharing" ([CC: Using CC-licensed Works for AI Training](https://creativecommons.org/using-cc-licensed-works-for-ai-training/)). Running Claude over a private copy of CC BY, BY-SA, CC0 or PD photos for internal evaluation is therefore within the licences.
- **Attribution in demos.** Any dashboard, deck or report that shows an image must credit the author, licence and source. `manifest.jsonl` stores all of these per image, plus Openverse's ready-made `attribution` string where one exists.
- **ShareAlike.** 69 of 117 sampled files are **CC BY-SA**. Seeded-FOD composites made from them (the spike's method) are adaptations, so if they are ever shared outside the team they must carry BY-SA. Prefer CC0, PD or CC BY backgrounds for synthetic insertion; the manifest's `sharealike` flag makes this a filter.
- **Rights the licence does not cover.** Commons notes that a free licence "does not affect any rights belonging to the subject of the photograph" and calls these "non-copyright restrictions" ([Commons: identifiable people](https://commons.wikimedia.org/wiki/Commons:Photographs_of_identifiable_people)). Ramp workers' faces and airline logos appear in most usable images. That is fine for internal testing, but flag it before external demos, especially any use of Delta livery that could imply endorsement.
- **Flickr API terms.** "Cache or store any Flickr user photos other than for reasonable periods" is prohibited. Apps must show "This product uses the Flickr API but is not endorsed or certified by SmugMug, Inc." The terms say nothing about ML ([Flickr API ToS](https://www.flickr.com/services/api/tos/)). A persistent test set fetched through the API therefore needs legal review. The CC licence permits keeping a copy, but the API terms govern how it was fetched. One alternative is to fetch only via Commons, where many Flickr CC images have already been imported, or to re-fetch at run time from the stored URLs.
- **Wikimedia client etiquette.** Make requests "in series rather than in parallel" and use `maxlag` for non-interactive jobs ([API:Etiquette](https://www.mediawiki.org/wiki/API:Etiquette)). The UA "should" include contact info such as an email, website or wiki user, and generic UAs "may be blocked without notice" ([User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)). As briefed, the prototype uses a generic UA with no personal info. That put it in the 10 req/min tier: I got a 429 after about 10 quick calls, and the script now spaces calls 6.5 s apart and honours `Retry-After`. A bulk run should use a team contact URL or address to get the 200 req/min tier. **That is a decision for the user.**
- **Licence filter as implemented.** Allowed: CC0, PD/PDM, CC BY (any version), CC BY-SA (any version). Rejected: NC, ND, GFDL-only, "Attribution" templates, fair use. Commons' own NC ban makes NC rejections rare there. About 30% of ATL files failed the filter; the reasons are now logged per licence string. The two categories I spot-checked were nearly all CC BY or BY-SA 2.0, plus 2 GFDL-only files.

## 3. Prototype manifest (`prototypes/image-archive/`)

- **`build_manifest.py`** runs query → licence filter → attribution record → sample download.
  - Sources: Commons full-text search (`generator=search`, File namespace, `filetype:bitmap`), Commons category-tree walk (`--category`, `--depth`) and Openverse (`license_type=commercial,modification`, `category=photograph`).
  - Filters: licence allowlist; JPEG/PNG only; width ≥ 1000 px; a title blocklist (cockpit, in flight, landing and similar).
  - Each `manifest.jsonl` row records `id`, `source`, `title`, `page_url`, `author`, `licence`, `licence_raw`, `licence_url`, `sharealike`, `attribution_required`, `restrictions`, `date_taken`, `width/height`, `download_url`, `query`, `angle_hint`, `set` (general/atl), `file`, `file_sha256` and `retrieved`.
  - Behaviour:
    - Resumable: ids already in the manifest are skipped.
    - `--shuffle-seed` gives reproducible random sampling.
    - `--dry-run` writes candidate lists to `manifest.dryrun.jsonl`, which holds the 374-row ATL listing.
  - Safety:
    - Downloads are decoded only with Pillow, capped at 40 MP, resized to ≤ 1600 px wide and re-encoded to JPEG, which strips embedded payloads.
    - Files are written only to `raw/`, and scripts live outside it.
    - Runs use `.venv/bin/python -I` with a uv venv (`pillow` is the only dependency).
- **`contact_sheet.py`** tiles images into numbered 2×3 sheets (`sheets/`) for the manual tagging pass.
- **`labels.csv`** has one row per image: `angle` (best fit or `none`), `also_covers`, `narrowbody_at_stand`, `light` (day/dusk/night), `wet`, `viewpoint` (raised/ground/window/cabin/aerial), `quality`, and notes on GSE clutter or debris.
- **Sample: 117 images, 35 MB.**
  - General set: 56 images (48 Commons, 8 Openverse/Flickr).
  - ATL set: 61 images (43 Commons, 18 Openverse/Flickr).
  - Licences: 69 BY-SA, 42 BY, 5 PD, 1 CC0.
  - Original width: median about 3,600 px, minimum 1,024.
- **Reproduce:**
  ```
  cd prototypes/image-archive
  uv venv .venv && uv pip install --python .venv/bin/python pillow
  .venv/bin/python -I build_manifest.py --per-query 5 --max 55          # built-in general query plan
  C="Hartsfield-Jackson Atlanta International Airport"
  .venv/bin/python -I build_manifest.py --set atl --shuffle-seed 13 --per-query 7 --max 60 --depth 1 \
    --category "Airbus A321 of Delta Air Lines at $C|ATL" --category "Airbus A320 of Delta Air Lines at $C|ATL" \
    --category "Airbus A319 of Delta Air Lines at $C|ATL" --category "Boeing 757 of Delta Air Lines at $C|ATL" \
    --category "Boeing 737 of Delta Air Lines at $C|ATL" --category "Airbus A220 at $C|ATL" --category "$C at night|ATL,NIGHT"
  .venv/bin/python -I contact_sheet.py
  ```
  Search results drift as Commons and Flickr change, so `manifest.jsonl` (with `file_sha256`), not the query, is the reproducible record.

## 4. Per-Angle yield (measured) and projected test-set size

### General sample (55 unique; #35 is a cross-source duplicate of #10)

| | NOSE | ENG-L | ENG-R | CARGO | AFT | WIDE | none |
|---|---|---|---|---|---|---|---|
| Best-fit Angle (of 55) | 7 | 0 | 0 | 8 | 0 | 8 | 32 (incl. poor-quality and wrong-type) |
| Usable images covering the Angle at all (of 23) | 12 (52%) | 1 (4%) | 6 (26%) | 12 (52%) | 0 (0%; 95% upper bound about 13%) | 14 (61%) | — |

- **Light and weather among the 23 usable:** 5 night or dusk (22%), 6 wet (26%).
- **Viewpoints:** 16 raised (terminal or garage), 3 window, 3 ground, 1 cabin.
- **What failed:** wrong type (widebodies, regionals, Fokker, Il-86, 1940s NASA photos), taxiing or airborne aircraft, window glare, and query false hits such as a 1944 "belt loader" mining conveyor.
- **Yield by query type:** gate-specific queries ("jet bridge A320 gate", "Boeing 737 at gate jet bridge", "A320 apron", "737-800 apron") gave 13/18. Generic night, rain, category and GSE queries gave about 20%.

### ATL sample (61; seeded random within each Commons category)

| Source / category | Files available (passing filter) | Sampled | Usable | Angles of the usable images |
|---|---|---|---|---|
| Commons: A321 of Delta at ATL | 89 | 7 | 0 (1 poor: #116, Sky Club window glare) | — |
| Commons: A320 of Delta at ATL | 57 | 7 | 1 (#87) | CARGO (+NOSE) |
| Commons: A319 of Delta at ATL | 43 | 7 | 1 (#93) | CARGO |
| Commons: 757 of Delta at ATL (tree) | 229 seen | 7 | 0 | — |
| Commons: 737 of Delta at ATL (tree) | 159 seen | 7 | 2 (#103 under tow, #106 at a B-gate) | NOSE; CARGO (+ENG-R, AFT) |
| Commons: A220 at ATL | 2 (jetBlue only; **no Delta A220 file**) | 1 | 0 | — |
| Commons: ATL at night | 19 | 7 | 1 (#112, 757 at gate at night) | WIDE (+CARGO) |
| Openverse (Flickr) "delta a321/737/757 atlanta" | 135 / 162 / 95 hits | 18 | 0 (16 are by one spotter, watermarked, taxiing) | — |
| **Total** | about 590 Commons + about 390 Openverse | 61 | **5 (8%; Commons 12%)** | CARGO 4, NOSE 2, WIDE 1, ENG-R 1, AFT 1 |

- Delta's Commons ATL categories are dominated by types outside the brief: MD-88 189, 767 59, MD-90 49, DC-9 38, 717 74.
- No sampled image is identifiable as Concourse T. Several taxiway shots show ATL concourse gates only in the far background.

### Empty stands and GSE staging (new pre-arrival use)

- General: 3/55 (5%). These are #14 and #15 (GSE with no aircraft) and #28 (empty jet bridges).
- ATL: 0/61.
- Targeted pulls of Commons *Jet bridges* (61), *Ground power units* (78), *Aircraft tugs* (98) and *Baggage handling* (38) should raise this. Not measured.

### Natural debris and GSE clutter (false-alarm tests)

- **Loose items worth adjudicating** (unverified at full resolution unless noted):
  - #4: small white loose items near the jet-bridge stairs (viewed at full resolution).
  - #16: bags on the ground beside the belt loader.
  - #47: a loose yellow strap and bag items on a belt loader.
  - #87 (ATL): bags on the ground beside a cart.
  - #1 and #2: oil and rubber stains on the stand.
  - The spike's own photos also contained a scrap at `pelita_pwl` and a mat at `wingo`. `wingo` reappears here as #9; exclude or tag it so spike and test data don't overlap.
- **Heavy legitimate GSE clutter:** #3, #4, #7, #9, #10, #12, #14, #15, #22, #38, #44, #49, #87, #106, #107 and #112. These include belt loaders, bag carts, ULDs, tugs, cones, GPU cables, catering hi-loaders and people.
- **Real FOD exemplars:** Commons *Foreign object damage* and *FOD walks* contain public-domain US military photos of FOD walks and debris on flight lines. They are useful as real-object references, not as gate scenes.

### Projection (Commons only; about 1,500 candidate downloads take about 10 minutes at 200 req/min, or about 2.5 hours at the anonymous 10 req/min)

| | NOSE | ENG-L | ENG-R | CARGO | AFT | WIDE |
|---|---|---|---|---|---|---|
| **General**: about 450–600 usable images. About 800 unique gate/apron hits × 40–60% yield, plus about 650 GSE/category files × about 20% | ~260 | ~20 | ~130 (mostly crops of WIDE/CARGO frames) | ~260 | 0–60 | ~300 |
| **ATL (Delta, in-scope types)**: about 25–70 usable. About 590 Commons files × about 12%; Openverse adds about 0 | ~10 | ~0 | ~5 | ~30 | ~5 | ~10 |
| **ATL Concourse T specifically** | ~0 | ~0 | ~0 | ~0 | ~0 | ~0 |

- Images count once per Angle they cover, because the 0005 Resolution allows an Angle to be a crop of a larger frame.
- Expect about 20% night or dusk and about 25% wet. Keep these ranges wide: the general sample is only n=23 and the ATL sample n=5.
- A Flickr API pass with licence IDs and an ATL `bbox` would add an unknown multiple. Its yield is likely nearer Openverse's (low; mostly spotter shots) than Commons gate queries.

## 5. Recommended next steps

1. **Decide the User-Agent contact.** A team URL or role mailbox, not a personal one, moves Commons from 10 to 200 req/min. Then run the bulk Commons pass: the built-in gate/apron queries plus the GSE categories, with about 1,500 candidates as a `--dry-run` first.
2. **Deduplicate.** Use perceptual hashing across sources. The sample already had one Commons/Flickr duplicate (#10/#35). Tag or exclude the 6 spike backgrounds.
3. **Tag at scale.** Tag each image with the Angle crops it can supply, not just one best fit. Claude can pre-tag from the contact sheets, with a human confirming each tag. Store the crop boxes in `labels.csv` so one WIDE or CARGO frame can yield several Angle images.
4. **Fill ENG-L and AFT elsewhere.** Use staged capture (0011) or synthetic insertion into those views. Internet photos will not supply them. Mirrored ENG-R images could stand in for ENG-L only as a labelled augmentation, never as real data.
5. **ATL Concourse T.** Ask ATL's or Delta's media teams for written permission to use stand photos, ideally empty-stand and staged-GSE shots (another agent is gathering ATL site facts). Optionally, with an approved Flickr key, run a `bbox` search around Concourse T with a `min_date_taken` limiting agent and licence IDs 4,5,7,8,9,10,11,12.
6. **Licence hygiene.**
   - Show attribution in the dashboard from `manifest.jsonl`.
   - Prefer non-SA backgrounds for synthetic composites.
   - Get a legal read on Flickr API caching if a Flickr pass is approved.
   - Check identifiable people and livery before any external demo.
7. **Build the empty-stand / GSE-staging set** as its own `--set prearrival` pass, since the sample's rate (5%) is too low to rely on incidental hits.

## Sources

- Commons licensing policy: https://commons.wikimedia.org/wiki/Commons:Licensing
- Commons, identifiable people / non-copyright restrictions: https://commons.wikimedia.org/wiki/Commons:Photographs_of_identifiable_people
- MediaWiki API etiquette: https://www.mediawiki.org/wiki/API:Etiquette
- Wikimedia API rate limits: https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
- Wikimedia User-Agent policy: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
- Flickr API terms: https://www.flickr.com/services/api/tos/
- Flickr licence IDs: https://www.flickr.com/services/api/flickr.photos.licenses.getInfo.html
- Flickr photos.search (api_key, license, per_page, 4,000-result cap, bbox/geo limits): https://www.flickr.com/services/api/flickr.photos.search.html
- Openverse API (OpenAPI schema: license / license_type / source params, auth and pagination limits): https://api.openverse.org/v1/ (schema at https://api.openverse.org/v1/schema/)
- Openverse source stats: https://api.openverse.org/v1/images/stats/
- Openverse terms of service: https://docs.openverse.org/terms_of_service.html
- Creative Commons, using CC works for AI training: https://creativecommons.org/using-cc-licensed-works-for-ai-training/
- DVIDS copyright / usage: https://www.dvidshub.net/about/copyright
- NASA images and media usage guidelines: https://www.nasa.gov/nasa-brand-center/images-and-media/
- USA.gov, government works and copyright: https://www.usa.gov/government-copyright
- Munich Airport media center (example press-gallery terms): https://www.munich-airport.com/media-center-264718
- YouTube terms of service: https://www.youtube.com/static?template=terms
- Measured counts: Commons Action API `list=search&srinfo=totalhits`, `prop=categoryinfo` and `generator=categorymembers`, queried 2026-11-13; prototype logs `prototypes/image-archive/run*.log`
