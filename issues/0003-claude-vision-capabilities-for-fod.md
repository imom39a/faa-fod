---
id: 3
title: "What can Claude's vision API actually do for multi-image FOD detection?"
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

From Anthropic primary docs: which current Claude models support image input; limits per request (image count, size, resolution, downscaling) and what that means for small debris in wide apron shots; documented ability/limits for spatial localisation (coordinates, bounding boxes); structured output / tool use for returning Findings as JSON; prompt caching for a reusable rule set; rough cost and latency for one Inspection of ~4–6 images. Flag differences if accessed via Bedrock/Vertex.

## Resolution

Findings: [research/claude-vision-capabilities.md](../research/claude-vision-capabilities.md).
- All current Claude models (Opus, Sonnet, Haiku 5.5) accept images. Each image is scaled down to at most 2576 px on the long side. 4–6 images per Inspection is far below the per-request limit.
- **Main risk:** small debris in wide shots shrinks to a few pixels after scaling. Anthropic's guidance is to crop, tile, or give the model a crop tool. No accuracy figures are published, so the spike (0007) must measure it.
- Pixel bounding boxes are supported but approximate, measured on the scaled image. Counts of many small objects are imprecise. Both support the human Confirmation step.
- Use structured outputs (a JSON schema) for Findings. Forced tool choice errors on Opus and Sonnet 5.5. Schema limits apply (at most 24 optional fields, no numeric min/max).
- Prompt caching for the rule set works, but saves little because images dominate the cost. Use the 1-hour cache TTL. A rule set under 512 tokens isn't cached.
- Estimated cost per 6-image Inspection: Opus ~$0.18 (tiled ~$0.32), Sonnet ~$0.09, Haiku <$0.01. No latency figures are published.
- Bedrock and Vertex: base64 images only, no Files API or batch. Bedrock caps images at 5 MB.
