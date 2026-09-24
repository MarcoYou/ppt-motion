# Choose motion by meaning

Start with the slide's takeaway and the visual variable that carries it. Use the existing object geometry to make that variable easier to read. More moving objects do not necessarily make a clearer explanation.

Choose among three purposes:

- **Quantity reveal:** expose the source encoding along its meaningful dimension, such as a bar's length, a line's progression or a donut's angle. Preserve its final values and geometry.
- **Explanation emphasis:** direct attention to a relationship or conclusion using a traced arrow, targeted highlight or one pulse of an existing callout.
- **Entrance:** bring a reading unit into view with a short fade or wipe. An entrance controls attention but does not explain the quantity in a chart.

If the user says a donut should fill around its ring, implement an angular color reveal. Making the whole chart fade more slowly does not satisfy that request. Carry this preference into equivalent chart types in later work, without turning a particular page, template or subject into a permanent exception.

## Object-to-motion choices

These are defaults to adapt to the user's requested style and the source geometry, not a requirement to animate every object.

| Object or encoding | Preferred motion | Keep stable / selection limits |
|---|---|---|
| Decoration, logos, borders, dividers, footer furniture | Static | They provide orientation; appearing first or moving repeatedly adds no explanation |
| Titles and reading text | Title visible from the start; optional short block entrance for narrative text | Do not animate glyph by glyph; keep units, data labels and footnotes readable |
| Simple vertical/horizontal bars | `bar-y` / `bar-x`, from the real zero baseline | Include negative bars on the correct side of zero; preserve axes, labels, thickness and final length |
| Stacked bars | Coordinated `bar-y` / `bar-x` growth from one actual zero baseline | Every segment shares origin and timing; independent segment origins or stagger break the cumulative relationship |
| Line series | `line`, tracing existing stroked paths in their source order | Keep axes, grid, markers and labels stable; retain dashes and series colors; inspect path direction |
| Donut, pie, circular gauge | `radial`, sweeping through the source sectors around a shared center | One sweep crosses all slices; leave center value, slice labels and legend fixed; optional neutral track makes color accumulation visible |
| Heatmap | `tile` on selected cell fills to reveal their existing colors in place | Keep cell geometry, values and legend stable; reveal together for comparison |
| Table | Static with `band`, `outline` or `underline` on a relevant row/cell | Do not grow cells or count up numbers; keep the full comparison readable |
| Narrative arrow or connector | Trace an existing unfilled stroked path when its direction supports the explanation | A filled arrow shape is not a line series; keep the explanation text visible |
| Existing callout, star or marker | Optional single `star` pulse, or a targeted highlight | Pulse the annotation, not data marks or the surrounding chart |
| Scatter, area, image or unsupported chart geometry | Static, optionally with targeted emphasis | Use a whole-object entrance only when the user needs it; it is not a substitute for a quantitative reveal |

For stacked charts, coordinated growth applies the same scale around the chart's actual zero to every segment, preserving cumulative proportions and touching boundaries throughout playback. Select all segment fills, outlines and shadows; share origin, duration, delay and easing. Using a different origin for each segment or staggering individual segments creates misleading gaps and separate growth. Keep labels static. A shared clipping reveal through an intact stack is another valid treatment, but the current `wipe` clips each selected leaf to its own bounds and cannot create it from separate segment leaves. If reliable selection or a common transform is unavailable, preserve the stack and emphasize the relevant part. Do not invent quantities or reconstruct a chart merely to give it motion.

For a donut or pie, use one page-space center, outer coverage radius, start angle, signed sweep angle and timing across every selected slice. Normally a complete ring starts at the top and sweeps clockwise once. Follow the source's angular extent for a partial gauge. The source defines slice proportions and the donut hole; the effect only reveals them. Do not rotate, scale or separately fade slices to imitate filling. Detailed fields and examples live in [object-workflow.md](object-workflow.md) and [configuration.md](configuration.md).

## Timing and fidelity

Default to simultaneous starts for objects being compared, then let the slide settle. A useful starting range is 700–1200 ms for quantitative reveals, 400–700 ms for a highlight or single annotation pulse, and 250–450 ms for a requested text entrance. Set timing explicitly when departing from the plan's defaults. Use a short stagger only when order carries meaning; avoid a long queue of entrances that delays reading. Effects do not loop or advance the slide.

Preserve final geometry, colors, line styles, labels and displayed values. Temporary motion is not an additional dataset: do not present an interpolated number as an observed value, or imply time evolution in a composition chart. Titles, axes and legends provide the context needed to interpret the moving mark.

Vector source leaves enable selective motion. A flattened image may combine chart, labels and background into one leaf; fading or wiping that image reveals pixels together, not independently understood data. Prefer a static source plus a precise highlight when reliable selection is unavailable, and record the limitation. Reconstruction needs suitable source data and must be part of the user's requested work.

Check start, midpoint and completion against the intended meaning: bars originate at zero, a radial boundary progresses continuously around the ring, line direction is sensible, and comparison labels remain readable. At completion, replay interruption, motion-off and reduced-motion states, the source should retain its exact final appearance.
