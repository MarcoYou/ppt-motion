# Build contract

The reusable skill lives in `skill/ppt-motion/`; scripts require Python 3.11+, PyMuPDF and lxml. Generated jobs are independent directories. No deployment is implicit.

## Job

`deck.json` schemaVersion 1 contains title, sourceHashes, slides. Each slide has page (original PDF page), title, message, motions, remove, emphasis. All coordinates are PDF points, `[left, top, right, bottom]`. `motions` entries have ids (exact inventory IDs), kind (fade/tile/bar-x/bar-y/line/radial/star/wipe), duration (ms), delay (ms), optional origin [x,y] in page space. `remove` is a list of exact inventory IDs. `emphasis` entries have kind outline/underline/band, box, color, width, duration, delay. Each motion rule targets exact leaves; source SVG transformations are retained. Rotated/skewed ancestors are excluded from transform effects unless explicitly supported. `inventory.json` lists each page's width, height, text and elements. Each element has id, type, bboxPt, visibleBboxPt, text, fill, stroke, matrix (full cumulative source transform), parentMatrix, fingerprint. `source/` contains input copies; `extracted/page-NNN.svg` is immutable geometry with data-leaf, data-bbox, data-parent-matrix metadata. Rectangle-only compound paths are split before inventory.

## Build output

`dist/deck.json`: title, slides [{page, title, message, width, height, svg:"assets/page-001.svg", reference:"reference/page-001.png"}]. Each SVG contains data-motion, data-duration, data-delay, optional data-origin; radial adds data-center, data-radius, data-start-angle, data-sweep-angle and optional data-track-color; data-bbox uses page coordinates, data-parent-matrix is six affine numbers. Emphasis paths/rects are grouped with `data-emphasis="true"`; animated outline paths use data-motion="line". Overlay node transforms are identity. `dist/index.html`, `viewer.js`, `viewer.css` are copied verbatim from skill assets. Relative links only; no remote dependencies. Motion final state must be original geometry plus declared removals/emphasis. Reference PNGs are original PDF renderings for comparison.

## Viewer

Generic variable dimensions, fit viewport; title, previous/next, slide select, replay, motion toggle, emphasis toggle, inspect toggle, comparison toggle, fullscreen. Arrow keys navigate; R replay; F fullscreen. Caption is message and hides in fullscreen. No autoplay slides or sequential spotlight focus. All default delays zero. Inspector click reports exact data-leaf ID + bbox, with a visible outline. Comparison shows original reference and current slide. Reduced motion and visibility changes settle all effects to final state; repeat/navigation must cancel stale animations. An optional accessible original text description lives in SVG. No external scripts or fonts.

## PPTX inventory module

`scripts/pptx_inventory.py` exports `read_pptx(path) -> dict`. No mutations. Return slide size in points, ordered slides (including hidden status), per-shape ID/name/kind/text and bbox when reliable; child groups and local vs page coordinate limitations explicit; chart references/cached series when available. PDF page mapping is not inferred unconditionally from slide count. Errors should be meaningful ValueErrors.

## Object plans (0.2)

`plan` writes `motion-plan.json` with source-lock/config hashes, profile, warnings, and slides of named components. Roles describe title/text/table/chart/image/annotation intent; an effect plus exact inventory IDs or an emphasis box specifies behavior. Metadata comes from native PPTX objects when page text uniquely agrees or a confirmed slide map is supplied. Equal counts never establish mapping. PDF-only/unresolved text regions remain static because they can be table labels. PPTX text blocks can fade under `explain`; titles and tables stay static by default.

`apply-plan` verifies both hashes and compiles every affected slide before atomically replacing deck.json; previous configuration is saved under history. Generated low-level motion/emphasis rules carry `componentId`. Replanning retains those component choices; applying a new revision replaces only rules owned by the listed component IDs, preserving unrelated/manual rules and page order. Set a component to static to remove its managed effect. Duplicate animation of the same leaf is still invalid. Component metadata is retained for future editing.

`doctor` is read-only. `init --pptx` can discover a sibling PDF. `export-pdf` is an explicit LibreOffice conversion into a new PDF using an isolated temporary office profile; it never edits the PPTX and never overwrites an existing PDF. The result is a candidate visual reference that requires font/chart/wrapping review, not a promise of identical native PowerPoint rendering.


## Radial reveal (0.3)

`radial` requires a shared page-space `center: [cx,cy]` and positive `radius` covering the source sectors. `startAngle` defaults to -90 (top), `sweepAngle` to 360 (clockwise); negative values reverse direction and zero or absolute sweeps above 360 are invalid. Optional `trackColor` is a hex6 neutral underlay used only during playback. Sector geometry, colors/patterns and center labels remain intact. Parent transforms are inverted to preserve page-space angles; numerically singular parents are rejected. Replay, completion, interruption and reduced motion remove temporary underlays and applied motion masks. Object plans preserve radial parameters; native pie/donut metadata suggests radial but never guesses the center or sector IDs.

## Installation and portable output (0.4)

`scripts/run.py` is the shared bootstrap entrypoint. It installs exact pins into a cached virtual environment keyed by requirements and Python/platform identity. `--setup` prepares or validates that runtime; `--help` and `--version` need only the standard library. The engine's direct `ppt_motion.py` entrypoint remains available for already provisioned environments. `install.py` copies the self-contained skill for Codex or Claude Code, detects managed/unmodified installations by a file manifest, and preserves prior installs in backups before replacement. It never installs Python packages globally.

`export-html JOB --out FILE.html` requires a current verified build. It embeds `{version:1, deck, assets}` in an inert JSON script element, SVG assets as text, and reference PNGs as base64 data URLs. HTML-significant characters in the JSON are escaped. Viewer CSS and JavaScript are embedded and the viewer reads bundled assets without network fetches. The final motion and comparison behavior matches the multi-file viewer. Export never overwrites an existing file or writes into managed source/build directories.

Claude Code loads the canonical `skill/` directory through `.claude-plugin/plugin.json`. Claude Desktop receives a ZIP with a top-level `ppt-motion/SKILL.md` tailored to uploaded inputs and downloadable output, sharing the same scripts, assets and motion references. `scripts/package_release.py` uses an explicit filename allowlist, deterministic ZIP metadata and SHA-256 checksums; source decks, private job folders, environment files and caches are excluded.

## OpenAI plugin distribution (0.5)

The repository retains a single canonical engine under `skill/ppt-motion`. A `.codex-plugin/plugin.json` compatibility manifest points to `./skill/`; `.agents/plugins/marketplace.json` loads the tagged GitHub release. Claude continues to use its own compatible marketplace metadata.

`ppt-motion-openai-plugin.zip` maps the canonical skill into conventional `skills/ppt-motion/` at packaging time and includes portable root `plugin.json`, an OpenAI compatibility manifest, a logo and policy documents. It contains no MCP configuration, hooks, screenshots, credentials or user decks. Public directory review and publication are separate from publishing this GitHub archive.
