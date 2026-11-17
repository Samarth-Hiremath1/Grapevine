## What this changes

## Checklist

- [ ] `uv run pytest -q`, `uv run ruff check grapevine tests studies examples`, `uv run mypy` pass
- [ ] `uv run mkdocs build --strict` passes, if docs changed
- [ ] Every new number traces to a committed run or a re-runnable script
- [ ] No committed run, or generator one depends on, is modified
- [ ] Public API changes: `__all__`, the API docs page and `CHANGELOG.md` updated
- [ ] New checks come with a planted-flaw fixture, and the control still passes
