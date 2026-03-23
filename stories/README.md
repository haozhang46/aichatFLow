# Stories Workspace

This directory stores persistent story projects for the `story-agent`.

Each story should live under its own folder:

```text
stories/
  <story-id>/
    story.json
    overview.md
    setting.md
    characters.md
    outline.md
    notes.md
    chapters/
      001-prologue.md
      002.md
```

Rules:

- `story.json` is the machine-readable source of truth for project state.
- Markdown files are the human-readable writing workspace.
- Keep `story.json` and the Markdown files in sync when revising.
- Read `story.json`, `outline.md`, and the most recent chapters before continuing a story.
