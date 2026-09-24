# Claude Desktop custom skill

Download `ppt-motion-claude-desktop.zip` from the repository's Releases. Enable **Code execution and file creation**, then open **Customize → Skills → + → Create skill → Upload a skill** and upload the ZIP without extracting it. Enable PPT Motion and attach a deck PDF, optionally with the matching PPTX, to a new conversation.

Example request: “Use PPT Motion on pages 2–4 of these uploaded slides. Preserve the design, grow the bars from zero, and return one downloadable HTML file.”

This is a custom skill for Claude's chat code-execution environment, including chat in Claude Desktop. It is not a Desktop extension, MCP server or local-file connector. If the app does not expose skill management, use the same account at [Claude's Skills page](https://claude.ai/customize/skills). Account and organization settings govern availability.

The ZIP contains one `ppt-motion/` folder with `SKILL.md`, scripts, references and viewer assets. Its instruction file is a Desktop-specific overlay; its engine and viewer are copied from the canonical `skill/ppt-motion/` source at release time. There is no second tracked engine.

Python 3.11+ and the pinned packages are required. First-run package installation needs network access; an isolated hosted environment can lose its cache between sessions. PPTX-to-PDF conversion additionally needs LibreOffice and is not guaranteed to be available or visually identical to PowerPoint. Upload a PDF exported from PowerPoint for a dependable visual reference. No paid Claude conversation has been used as a release test: packaging, the local engine and the single-file export are tested separately.

Official installation and format references:

- [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
- [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)

Build this artifact from the repository root with `python3 scripts/package_release.py`. The release builder only copies explicitly allowed files; source decks, generated jobs, local runtime caches and QA artifacts are excluded.
