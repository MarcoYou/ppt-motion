# Title, text, table and chart workflow

A job belongs to one source deck. The skill and its recipes are shared across jobs; page numbers, coordinates, plot origins and messages are always derived from that job.

## Editable object plan

`plan JOB --profile research` creates `JOB/motion-plan.json`. It never replaces an existing plan. To start another pass, use `plan JOB --out JOB/motion-plan-v2.json`. Then `apply-plan JOB --plan JOB/motion-plan-v2.json`.

The plan records source-lock and deck hashes. Its `slides` retain source PDF page numbers. Each component has a unique `id`, `role`, `label`, `box` and selected source `ids`. `effect` is the actual instruction; `suggestedEffect` is only a hint. PDF coordinates use `[left, top, right, bottom]` in points.

Supported roles: `title`, `text`, `table`, `bar-chart`, `line-chart`, `chart`, `heatmap`, `image`, `annotation`, `shape`.

Profiles:

- `research`: all content remains visible; choose chart motion and message emphasis selectively.
- `explain`: mapped narrative PPTX text blocks fade together; short labels and footer furniture stay static; titles, tables and charts remain static until reviewed. Unresolved PDF-only blocks remain static because table labels cannot be reliably distinguished.
- `static`: explicitly no initial motion; useful for dense pages or a baseline comparison.

PPTX native table rows/columns/merges and cached chart types help identify objects. Caches are metadata, not independently verified live data. Inherited layout bounds, SmartArt and flattened images may need manual regions. Equal PDF/PPTX slide counts do not prove ordering. `plan JOB --slide-map 1=1,2=3` supplies confirmed PDF-page=PPTX-slide pairs; hidden PPTX slides may be absent from the PDF. An unresolved page still gets PDF text-block candidates.

## Recipes

Choose the intended quantity reveal, explanation emphasis or entrance using [motion-language.md](motion-language.md). Edit components using IDs from the current job. Coordinates below are examples, not reusable deck selectors.

```json
{
  "id": "main-comparison",
  "role": "bar-chart",
  "label": "Quarterly change, positive and negative",
  "box": [80, 120, 480, 390],
  "ids": ["p02-e0010", "p02-e0011"],
  "effect": "bar-y",
  "origin": [80, 280],
  "duration": 900,
  "delay": 0
}
```

- **Bar:** `bar-y` for vertical bars, `bar-x` for horizontal. `origin` must lie on the real zero axis. For stacked bars, include every segment fill, outline and shadow in coordinated growth with exactly the same zero origin, duration and delay. The common transform preserves cumulative proportions and touching segment boundaries; never use each segment's own lower edge or stagger the segments. Keep labels static. A shared clipping reveal is an alternative only if it can be represented faithfully: the current `wipe` uses each leaf's bounds, so separate segment wipes are not a shared stack reveal. Log axes and truncated baselines need an explicitly justified alternative.
- **Line:** `effect: "line"` and only actual stroked, unfilled series paths. Avoid grid lines, legend swatches, border paths and data-label glyphs. Preserve multiple series; use the same delay for simultaneous comparison.
- **Donut/pie/gauge:** `role: "chart", effect: "radial"` reveals existing filled vector sectors around one center. Select the sector fills and any matching outlines, excluding center text, labels, legends and footers. All slices of one chart share `center`, `radius`, `startAngle`, `sweepAngle`, duration and delay. An optional neutral `trackColor` makes the existing ring appear to fill with color. This is an angular source reveal; it does not regenerate data or count the displayed value upward.
- **Heatmap:** `role: "heatmap", effect: "tile"` and exact cell fill IDs reveal the existing color in place. Keep values, grid outlines and legends static when separately selectable. Short stagger requires separate component/rule delays; do not infer a heatmap from table cells alone.
- **Title/body:** leave titles stable. When a text entrance is useful, `effect: "fade"` animates all selected glyphs at the same time, reading as one block. Default duration is 450 ms. Highlight one sentence with a separate `annotation` and `underline` instead of hiding surrounding text.
- **Narrative arrow/callout:** use `line` on an existing stroked arrow shaft when its source path direction matches the explanation; a filled arrow is not a traceable line. An existing marker can use `star` for one brief scale pulse. Keep callout text readable and avoid pulsing a whole chart or its data marks.
- **Table:** leave its component `static`. Add a separate `annotation` for the important row or cell:

```json
{
  "id": "key-result-row",
  "role": "annotation",
  "label": "The row that supports the slide's conclusion",
  "box": [520, 240, 875, 278],
  "ids": [],
  "effect": "band",
  "color": "#276452",
  "opacity": 0.10,
  "duration": 650
}
```

For a donut, use one component containing all slices so the sweep crosses slice boundaries continuously:

```json
{
  "id": "allocation-ring",
  "role": "chart",
  "label": "Composition shown by the existing donut sectors",
  "box": [200, 110, 440, 350],
  "ids": ["p03-e0021", "p03-e0022", "p03-e0023"],
  "effect": "radial",
  "center": [320, 230],
  "radius": 121,
  "startAngle": -90,
  "sweepAngle": 360,
  "trackColor": "#E3E5E7",
  "duration": 1100,
  "delay": 0
}
```

The radius covers the outer edge of the selected geometry, including its stroke. `startAngle` is measured clockwise from the page's rightward axis; `-90` starts at the top. Positive `sweepAngle` is clockwise and negative is counterclockwise. A partial gauge can use its actual angular span. See [configuration.md](configuration.md) for radial field constraints and transformed geometry.

`outline`, `underline` and `band` use their `box` and can have no source IDs. Highlight colors should suit the deck. They remain visible after their entrance and can be disabled in the viewer. `static` preserves the component. `fade`, `wipe`, `star`, `tile`, `line`, `radial`, `bar-x` and `bar-y` act on selected source IDs; unsupported selections fail before the config changes.

When editing regions, inspect the PDF and use `inspect JOB --page N --box l,t,r,b --type path` to obtain candidates. A component's selected elements must belong inside its box. A leaf can receive one motion only, even across overlapping components or existing low-level rules. An effect plan does not remove old annotations automatically: use explicit `deck.json.remove` IDs when replacing them.

## Repeat on another deck

Create a new job, generate a fresh object plan, carry over the **role/effect choices** you liked, and select the new deck's objects. Do not copy source IDs, boxes, messages, data-axis origins or radial centers/radii from another job. Replanning retains previous component choices, including timing, geometry parameters and custom annotations. Applying a revision updates only its own component effects and preserves manual/unrelated rules; setting an effect to `static` removes that component’s managed effect. `apply-plan` backs up the previous config under `history/` and rejects stale plans. Build/check/review can then be repeated without rewriting a slide-specific animation script.
