# Configuration

For ordinary title/text/table/chart work, start with [object-workflow.md](object-workflow.md) and its `motion-plan.json`. `apply-plan` compiles reviewed objects into `deck.json`; direct `deck.json` edits remain supported. `source-lock.json`, source inputs, extracted SVGs, inventory and reference PNGs are immutable inputs. `dist` is rebuilt as a unit. Keep source locks; they are the guard against stale element selectors.

All coordinates are **PDF points**, origin at top-left, not screen pixels. `bboxPt` is `[left, top, right, bottom]`; bounds of curves are conservative control-point bounds. Inventory IDs are stored as SVG **`data-leaf`**, not native `id`; inspect with `[data-leaf="p02-e0001"]`. A logical bar or star may have separate fill and outline IDs. Transformed groups are represented by cumulative matrices in inventory.

```json
{
  "page": 2,
  "title": "Quarterly performance",
  "message": "A concise takeaway for the presenter.",
  "motions": [
    {"ids": ["p02-e0001"], "kind": "bar-y", "origin": [120, 300], "duration": 1000},
    {"ids": ["p02-e0002"], "kind": "line", "duration": 1150},
    {"ids": ["p02-e0003"], "kind": "tile", "duration": 450, "delay": 100}
  ],
  "remove": [],
  "adjust": [],
  "emphasis": [
    {"kind": "outline", "box": [100, 120, 180, 300], "color": "#ff0000", "width": 1.5, "duration": 1150}
  ]
}
```

IDs above illustrate syntax only; use IDs from the current job. Root fields are `schemaVersion: 1`, `title`, `sourceHashes`, `slides`. Retain generated `sourceHashes`. Reorder or omit entries in `slides` only if requested. A source page can appear once in the current schema.

| Field | Meaning |
|---|---|
| `motions[].ids` | Exact, unique inventory leaf IDs; each leaf gets at most one motion |
| `kind` | `fade`, `tile`, `bar-x`, `bar-y`, `line`, `radial`, `star`, `wipe` |
| `origin` | Required for bars: page-space `[x,y]` on the actual zero line; optional for star, which otherwise uses element center |
| `center`, `radius` | Required for `radial`: page-space `[cx,cy]` and positive outer coverage radius in PDF points |
| `startAngle`, `sweepAngle` | Radial angles in degrees: defaults `-90` and `360`; zero points right, positive sweep is clockwise, negative is counterclockwise |
| `trackColor` | Optional radial track color `#RRGGBB`; neutral copies of the selected filled vector sectors appear behind the reveal during playback and are removed on settle |
| `duration`, `delay` | Milliseconds, 1–10000 and 0–10000 respectively; defaults 900 and 0 |
| `remove` | Explicit source leaf IDs to delete, including every fill/outline leaf of an unwanted mark |
| `adjust` | Entries `{ "ids": [...], "dx": 0, "dy": -1, "reason": "Align the unit label" }`, translations in page points |
| `emphasis` | Entries with `kind`: `outline`, `underline` or `band`; `box`; optional color `#RRGGBB`, width, delay, duration, `animate: false` |
| Band opacity | `opacity` default 0.12; remains translucent in the final frame |

`line` requires a stroked, unfilled SVG path. It uses a temporary reveal mask, preserving the original dashes. `tile` reveals the existing cell color through opacity; it does not interpolate numeric values. `star` is a single scale pulse for an existing annotation. `wipe` and `fade` are generic source entrances: choose them only when that entrance serves the message, not as a substitute for unavailable quantity motion. See [motion-language.md](motion-language.md) for chart-specific choices and static fallbacks.

Bar/star/wipe through rotated or skewed **parent** groups are conservatively rejected by the builder; source shape transforms remain untouched. Radial reveals support any invertible parent transform: the page-space sweep is mapped into each source parent's coordinates with its inverse. The runtime settles all effects to the original final state when motion is disabled or reduced motion is requested.

## Radial source reveal

```json
{
  "ids": ["p03-e0021", "p03-e0022", "p03-e0023"],
  "kind": "radial",
  "center": [320, 230],
  "radius": 121,
  "startAngle": -90,
  "sweepAngle": 360,
  "trackColor": "#E3E5E7",
  "duration": 1100,
  "delay": 0
}
```

Select only the filled vector sectors of a donut, pie or gauge and their matching outline leaves. Keep center text, values, labels, legends and surrounding furniture outside `ids`. Use one rule for all slices, or identical center/radius/angle/timing parameters across rules, so one angular boundary crosses the entire chart. Independently sweeping each slice misrepresents the composition.

`center` is the chart's center in PDF page coordinates, not each slice's bounding-box center. Set `radius` to cover the outermost selected painted edge; it is the mask's coverage radius, not a replacement chart radius. Choose a nonzero `sweepAngle` with magnitude at most 360 degrees. For a partial gauge, the chosen start and sweep must cover every selected source sector; otherwise unrevealed geometry would appear suddenly at settle. A full sweep is the default for a complete ring or pie.

The temporary angular mask reveals original source geometry without rebuilding values, changing sector angles or morphing shapes. Optional `trackColor` places neutral vector copies behind the moving color boundary; omit it to reveal against the source background. Tracks and masks are removed at completion, on interruption and when motion is disabled, restoring the original composition. A raster image cannot provide independently selectable sectors or a reliable recolored vector track; leave it static unless a supported whole-image entrance is specifically useful. Do not describe a raster fade as ring filling.

## Source and viewer constraints

Disjoint compound rectangles are split at extraction into individual source leaves. This does not move coordinates. Overlapping compound paths are not split because fill winding can affect their appearance. `proposals.json` can match axes or table cells: it is only a starting point for inspection.

The built viewer includes replay (R), previous/next arrows, fullscreen (F), motion/ emphasis toggles, original comparison and click-to-inspect IDs. Fullscreen hides the external `message` block while keeping slide-native footnotes. The preview server binds only to `127.0.0.1`; Ctrl-C stops it.

If a deck has complex masks or unsupported SVG geometry, report the extractor limitation rather than dropping content. Fonts become paths, so browser display is stable but slide text is not editable like native PowerPoint; accessible source text is retained in SVG descriptions. Native PPTX animation and automatic financial inference are outside this tool's output contract.
