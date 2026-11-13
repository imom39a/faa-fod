# Claude vision capabilities for multi-image FOD detection

Resolves ticket [0003](../issues/0003-claude-vision-capabilities-for-fod.md). Researched 2026-11-13 against Anthropic's platform docs (platform.claude.com, where docs.anthropic.com now points). Each claim cites its source page. Anything marked **[estimate]** or **[inference]** is my own reasoning and is not stated in the docs.

## TL;DR

- **Every current model takes image input.** For this PoC the realistic choices are Opus 5.5, Sonnet 5.5 and Haiku 5.5. All of them are on the high-resolution tier, which handles up to 2,576 px on the long edge and 4,784 visual tokens per image.
- **Request limits are not a constraint.** 4–6 images is far below the 600-image cap. Above 20 images per request a stricter per-image size limit applies, which matters if we tile.
- **Small debris in wide shots is the main technical risk.** Claude downscales any image above the tier limits, so a 4K frame drops to 2576×1449. A bolt or tag a few cm across may end up only a few pixels wide, much smaller than one 28×28 visual patch. Anthropic's own guidance for small targets is to crop or tile, or give the model a crop tool.
- **Localisation works, but it is approximate.** Claude returns absolute pixel `[x1,y1,x2,y2]` boxes measured on the image *after resizing*. The docs say to ask for pixel coordinates, not normalised ones, and to verify the results. They also call counting large numbers of small objects imprecise.
- **Structured Findings JSON is a GA feature on all platforms.** Use `output_config.format` (JSON schema) or `strict: true` tools. Opus 5.5 and Sonnet 5.5 reject forced `tool_choice`.
- **Caching the rule set works but saves very little.** Images dominate the token count, and the minimum cacheable prefix is 512 tokens on the 5.5 models.
- **Cost per Inspection [estimate]:** about $0.18 (Opus 5.5), $0.09 (Sonnet 5.5) or under $0.01 (Haiku 5.5) for 6 untiled 4K frames. Tiling roughly doubles this.
- **Latency is not documented as numbers.** The docs only give relative labels. Measure it in spike 0007.
- **Bedrock and Google Cloud (Google managed) accept base64 images only.** Neither has the Files API, URL image sources or the Message Batches API. Bedrock caps each image at 5 MB (10 MB elsewhere). Fable 5.2 is not available on Bedrock.

## 1. Which models support image input

- "All current models support text and image input, text output, multilingual capabilities, vision, and tool use." — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- "Vision (images) is available on every model." — [Vision › Availability](https://platform.claude.com/docs/en/build-with-claude/vision)
- Current lineup ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)):

| Model | API ID | Comparative latency | Input / output $ per MTok | Default effort |
|---|---|---|---|---|
| Claude Fable 5.2 | `claude-fable-5-2` | Moderate | $8 / $40 | high |
| Claude Opus 5.5 | `claude-opus-5-5` | Moderate | $4 / $20 | medium |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | Fast | $2 / $10 | high |
| Claude Haiku 5.5 | `claude-haiku-5-5` | Fastest | from $0.10 / $0.50 (prompts ≤100K tokens) | medium |

- The Opus 5.5 model page lists "vision-heavy workflows" as a typical use. On Opus 5.5, thinking is always on and `effort` is the only control. — [Opus 5.5 overview](https://platform.claude.com/docs/en/models/opus-5-5/overview), [What's new in Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5)

## 2. Request limits, size, resolution, downscaling

Source: [Vision › Image limits and costs](https://platform.claude.com/docs/en/build-with-claude/vision) unless noted.

| Limit | Value |
|---|---|
| Images per API request | 600 (100 for 200K-context models). The 5.5 models have 1M context, so 600 applies. |
| Max dimensions per image | 8000×8000 px |
| Many-image rule | If a request has **more than 20 image blocks**, a stricter per-image dimension limit applies. This count includes images resent from earlier turns. To stay safe on every platform, keep each image at most 3,000 px per side, or send no more than 20 images. |
| Max size per image | 10 MB base64 (Claude API, Google Cloud Google-managed); **5 MB base64 on Amazon Bedrock** |
| Total request size | 128 MB on the first-party API. Other platforms set their own limits, and Bedrock's is lower. |
| Formats | JPEG, PNG, GIF, WebP (only the first frame of an animation is used) |
| Image metadata | Not read. "Claude does not parse or receive any metadata from images." EXIF data such as gate, camera or timestamp therefore has to go in the prompt text. |

**Resolution tiers:**

| Tier | Models | Max long edge | Max visual tokens |
|---|---|---|---|
| High-resolution | Claude 4.7 and later (includes Opus/Sonnet/Haiku 5.5) | 2,576 px | 4,784 |
| Standard | All other models | 1,568 px | 1,568 |

- The model processes 28×28 px patches, and each patch is one visual token. Cost = `⌈w/28⌉ × ⌈h/28⌉` tokens.
- An image that exceeds either limit is downscaled, keeping its aspect ratio, to the largest size that fits both. "For nearly all photos … the visual token limit is what determines the final size." — [Coordinates and bounding boxes](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates)
- Worked examples on the high-res tier: 1920×1080 is not resized (2,691 tokens). 3840×2160 is resized to 2576×1449 (4,784 tokens).
- The `transformations: {"oversized_image": "error"}` field on an image block makes the API return a 400 instead of silently downscaling. This is useful to keep the coordinate mapping honest. — [Coordinates](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates)
- Accuracy warning: "Claude might hallucinate or make mistakes when interpreting low-quality, rotated, or very small images under 200 pixels." Lossy compression artefacts "can be detrimental". — [Vision › Limitations / Image quality](https://platform.claude.com/docs/en/build-with-claude/vision)
- Put images before text. Label each image ("Image 1: Gate 12, camera NE"). Claude analyses multiple images jointly. — [Vision › Multiple images](https://platform.claude.com/docs/en/build-with-claude/vision)

### What this means for small debris in wide apron shots [inference]

- Suppose a 4K camera covers roughly 40 m of apron across its width. That is about 1 cm per pixel natively, and about 1.5 cm per pixel after Claude downscales to 2576 px. A 5 cm bolt then covers about 3 px, roughly a tenth of one 28 px patch. Detection at that size is not something the docs promise. They point the other way: "Small elements lose precision when an image is downscaled: for fine targets, crop the region of interest and send the crop … or use a high-resolution-tier model." — [Coordinates](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates)
- Mitigations the docs support:
  1. **Tile client-side** to at most 2576 px long edge and at most 4,784 tokens per tile, so nothing is downscaled. For example, a 4K frame cut into a 2×2 grid gives 1920×1080 tiles at 2,691 tokens each. 6 frames × 4 tiles = 24 images, which is over 20, so each tile must stay at or below 3,000 px. 1920 px tiles meet that.
  2. **Use a crop or zoom tool.** "Testing has shown consistent uplift on image evaluations when Claude is able to 'zoom' in on relevant regions." The docs link a [crop tool recipe](https://platform.claude.com/cookbook/multimodal-crop-tool). — [Prompting best practices › Improved vision](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices). For Opus 5.5 the docs add: "Higher-resolution images help … So do image-processing tools … a cropping tool alone still helps … The model uses these tools more effectively at higher effort levels." — [Prompting Claude Opus 5.5 › Tools for complex visual inputs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)
  3. **Two passes:** first send the whole frames to pick candidate regions, then send high-resolution crops of those regions for a re-check. Spike 0007 should decide between this and a single pass.
- The camera choice (ticket 0005) affects detection directly. A narrower field of view per camera, or more cameras, improves small-object detection more than any prompt change will.

## 3. Spatial localisation (coordinates and bounding boxes)

Source: [Coordinates and bounding boxes](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates) and [Vision › Limitations](https://platform.claude.com/docs/en/build-with-claude/vision).

- **What is supported:** "Claude can locate and label regions of an image (for example, returning bounding boxes …)".
- **Format:** "Claude works best with absolute pixel coordinates … `[x1, y1, x2, y2]` … Claude does not work well when you ask for normalized coordinates (e.g. 0–1000)." Normalise in our own code instead.
- **Coordinate frame:** the origin is top-left, x increases to the right and y increases downward. Coordinates refer to the *image Claude processed*, which means after any resize. Claude then pads the image to a multiple of 28 px on the right and bottom. Always rescale by the resized dimensions, never the padded ones.
- **Recommended pattern:** pre-resize, or tile, so the image we send is exactly the image Claude sees. Then the returned pixels map 1:1 onto it. Add `oversized_image: "error"` to catch drift if the camera or model changes. For a tile, add the tile's origin offset back to get frame coordinates.
- **Limits:**
  - "Claude's coordinate and localization outputs are approximate … verify outputs before relying on them."
  - "Claude can give approximate counts … might not always be precisely accurate, especially with large numbers of small objects."
  - "Do not use Claude for tasks requiring perfect precision … without human oversight."

  These limits fit our model, where a Verdict is advisory until a human Confirmation.
- **Highlight form for 0007 [inference]:** a pixel bounding box is supported, but the docs call it approximate. Spike 0007 should measure box quality (IoU) against a coarser fallback such as a grid cell or rough region before we commit to one.

## 4. Structured output and tool use for Findings JSON

Source: [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

- **Availability:** "Structured outputs are available on every model". The Messages API supports it on "All supported platforms", which includes Bedrock and Google Cloud (both list it in their feature support sections).
- **Two mechanisms:**
  - JSON outputs via `output_config.format` with a JSON schema. The docs' own example is "extract data from images". The SDK helper `client.messages.parse()` validates the response.
  - Strict tool use with `strict: true`.

  Both use grammar-constrained sampling.
- **Forced tool choice is rejected on Opus 5.5 and Sonnet 5.5.** `tool_choice: any` and `tool_choice: tool` "return a 400 error" on Fable 5.2, Opus 5.5 and Sonnet 5.5. Use `output_config.format`, or `auto` plus `strict: true`. — [Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- **Schema limits that affect the Finding schema (ticket 0010):**
  - Not supported: recursive schemas, numeric constraints (`minimum`/`maximum`), `minItems` above 1.
  - At most 24 optional parameters across all strict schemas in a request, and at most 20 strict tools.
  - Very complex schemas can fail with "Schema is too complex for compilation" (there is a 180 s compile timeout).
  - Keep Finding fields `required` and use `enum` for category and severity. Validate box bounds in code.
- **Latency side effect:** the first request with a new schema pays a grammar-compile delay. The compiled grammar is then cached for 24 h from last use. Changing `output_config.format` invalidates the prompt cache.
- **Incompatible with:** Citations (400 error) and assistant prefill.
- **Refusal handling:** a schema property that asks for "the model's thinking or step-by-step reasoning" can trigger a `reasoning_extraction` refusal. Ask for a short `rationale` instead.

## 5. Prompt caching for a reusable rule set

Source: [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).

- **Where to cache:** put the FOD rule set (from 0006) and the instructions in `system`, and put the tool and schema definitions in `tools`. Then place a `cache_control` breakpoint, or use top-level automatic caching. Render order is `tools → system → messages`, and a change at any level invalidates that level and everything after it.
- **Effect of per-Inspection images:** adding or removing images invalidates **only the messages cache**. The tools and system caches stay valid, so the rule set keeps hitting the cache even though every Inspection sends new images.
- **Minimum cacheable prefix:** 512 tokens on Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.2. A shorter prefix is silently not cached. Check `usage.cache_read_input_tokens` to confirm.
- **TTL:** 5 minutes by default, refreshed free on each hit. A 1 h TTL is available. Pricing:

  | | 5 min write | 1 h write | Cache read |
  |---|---|---|---|
  | Cost vs. base input | 1.25× | 2× | 0.05× on Opus 5.5 and Sonnet 5.5 ($0.20 and $0.10 per MTok) |

  With 6 gates and two Inspections per Turn, traffic may arrive more than 5 minutes apart. The 1 h TTL is likely the better fit **[inference]**.
- **Parallel requests:** a cache entry only becomes available after the first response starts, so warm the cache before sending parallel Inspections.
- **Second-pass reuse:** caching also helps a multi-pass flow. Cache the image block after pass 1 so the re-check reads the images from cache. All four breakpoint slots can be used.
- **Bedrock caveats:** Bedrock sets its own per-model minimums and usage-field names (see the AWS docs). The legacy `bedrock-runtime` endpoint rejects top-level automatic `cache_control`, so use explicit breakpoints there.

## 6. Rough cost and latency per Inspection

### Cost [estimate]

Assumptions:
- Rule set and instructions: about 3,000 tokens, cached (read price).
- About 500 tokens of per-Inspection text.
- About 3,000 output tokens (adaptive thinking plus Findings JSON). I am assuming thinking is billed at the output rate; verify against `usage`.
- Image tokens from the [Vision](https://platform.claude.com/docs/en/build-with-claude/vision) formula; prices from [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).

| Scenario | Image tokens | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|---|---|
| A: 6 × 4K frames, downscaled (6 × 4,784) | 28,704 | ≈ $0.18 | ≈ $0.09 | ≈ $0.005 |
| B: 6 × 4K frames tiled 2×2 (24 × 2,691) | 64,584 | ≈ $0.32 | ≈ $0.16 | ≈ $0.008 |
| C: 4 × 1080p frames (4 × 2,691) | 10,764 | ≈ $0.11 | ≈ $0.05 | ≈ $0.003 |

- Images dominate input cost. Caching the 3K-token rule set saves about $0.01 per Inspection on Opus.
- The Message Batches API halves the price, but "most batches complet[e] within 1 hour", with up to 24 h allowed. That suits offline evaluation runs, not live gate Inspections. — [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
- Haiku 5.5 prices rise for prompts over 100K tokens. All three scenarios stay under that.
- US-only `inference_geo` adds 10% to all prices. On Bedrock, regional endpoints add 10%. On Google Cloud, multi-region and regional endpoints add 10%.
- Use `count_tokens` on real images to re-baseline the token counts.

### Latency

- **No numbers are published.** The docs give only relative labels: Opus/Fable "Moderate", Sonnet "Fast", Haiku "Fastest". "Actual latency depends on prompt length, output length, and thinking effort." — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- **Documented levers:**
  - Pick a smaller model.
  - Lower `effort` (Opus 5.5 defaults to `medium`).
  - Keep output short and set `max_tokens`.
  - Stream the response. — [Reduce latency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)
  - Pre-resize images ("To minimize latency … prefer resizing images before uploading them").
  - Use the Files API so payloads stay small. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
  - Use caching.
  - Opus 5.5 fast mode: up to 2.5× output tokens per second at $8/$40.
- **Effort and tools:** Opus 5.5 "tends to think more per turn" at a given effort. A crop-tool loop adds round-trips.
- **Action:** spike 0007 should record wall-clock time per Inspection for each candidate model and effort level.

## 7. Bedrock and Google Cloud (Vertex) differences

| Aspect | Claude API | Amazon Bedrock (Mantle) | Google Cloud (Google managed, "Vertex") |
|---|---|---|---|
| Image source types | base64, URL, Files API `file_id` | **base64 only** | **base64 only** |
| Per-image size | 10 MB | **5 MB**, plus a lower total request size | 10 MB |
| Many-image (>20) count | images only | images **and PDFs** count | images **and PDFs** count |
| Files API | yes | no | no |
| Message Batches API | yes | no | no |
| Structured outputs | yes | yes | yes |
| Prompt caching | yes (512-token min on the 5.5 models) | yes, with AWS-documented minimums and fields; legacy `bedrock-runtime` has no automatic caching | yes (same minimums as the Claude API) |
| Server-side `fallbacks` | yes | no (client-side pattern only) | no (client-side pattern only) |
| Models | all | no Fable 5.2 or Mythos 5.2; access criteria vary by model | regional endpoints serve Sonnet 4.6 and earlier only, so the 5.5 models need the global or `us`/`eu` multi-region endpoint |
| Model ID | `claude-opus-5-5` | `anthropic.claude-opus-5-5` | `claude-opus-5-5` |
| Pricing | Anthropic list | AWS pricing (regional +10%) | Google pricing (multi-region and regional +10%) |

Sources: [Vision › Availability and limits](https://platform.claude.com/docs/en/build-with-claude/vision), [Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock), [Bedrock (bedrock-runtime)](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy), [Google Cloud (Google managed)](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed), [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview).

Two hosted options keep feature parity with the first-party API: Claude Platform on AWS and Claude Models on Google Cloud (Anthropic managed). Vision lists both as fully available. If the airline needs to stay inside AWS or GCP and also wants the Files API or Batches, these are worth a look.

## Risks and open questions

1. **Small-object recall.** This is the core risk, and no doc quantifies it. Measure it in 0007 with untiled, tiled and crop-tool variants.
2. **Box precision.** The docs call boxes "approximate". Keep the human Confirmation step, and choose the highlight form from measured IoU.
3. **False alarms.** The docs give no false-positive data for cluttered aprons with chocks, cones, hoses and painted markings. The rule set needs explicit "expected equipment" exclusions, and 0007 must measure false alarms.
4. **Lighting and weather.** The docs warn about blurry, low-quality and heavily compressed images. Night, rain and glare are untested.
5. **Platform lock-in.** If the airline requires Bedrock, we lose the Files API, Batches and 10 MB images (5 MB is tight for 4K PNG, so use JPEG or WebP and check for compression artefacts).
6. **Latency** is unmeasured, and depends heavily on model, effort and passes.

## Sources

- https://platform.claude.com/docs/en/build-with-claude/vision
- https://platform.claude.com/docs/en/build-with-claude/vision-coordinates
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/models/opus-5-5/overview
- https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/build-with-claude/batch-processing
- https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency
- https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock
- https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy
- https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed
