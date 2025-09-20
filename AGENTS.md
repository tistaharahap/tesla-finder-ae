# Repository Guidelines

## Project Structure & Module Organization
- `src/tesla_finder_ae/main.py` hosts the Typer CLI that drives digests, HTML output, and default marketplace URLs.
- `src/tesla_finder_ae/nodes.py` defines the Pydantic graph, MCP integration, and listing models—extend data logic here.
- `src/tesla_finder_ae/html_generator.py` renders Tailwind-based reports and JSON payloads consumed by `public/`.
- `public/` stores the generated `index.html` and `listings.json`; treat them as build artifacts checked into git.
- `README.md` documents supported workflows; align new features and examples with those instructions.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` creates the local environment before installing dependencies.
- `pip install -r requirements.lock` installs runtime packages; add `-r requirements-dev.lock` when working with LLM tooling.
- `python -m src.tesla_finder_ae.main digest` runs the consolidated digest across the curated URL list.
- `python -m src.tesla_finder_ae.main digest --html-report` regenerates `public/` assets and starts the lightweight preview server.
- `python -m src.tesla_finder_ae.main search "<listing-url>"` debugs a single source without touching stored artifacts.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints; keep modules `snake_case` and Typer commands short verbs.
- Prefer Pydantic models and dataclasses to raw dicts, and reuse helpers from `observability.py` for logfire spans.
- Keep HTML classes Tailwind-compatible and avoid embedding large assets; reference URLs in JSON instead.

## Testing Guidelines
- Establish tests under `tests/` mirroring module names (e.g., `tests/test_nodes.py`) once functionality stabilizes.
- Adopt `pytest` with `pytest-asyncio` for coroutine coverage; pin them in `requirements-dev.lock` when introduced.
- Prioritize parsing utilities, MCP call wrappers, and HTML generation functions for initial coverage.

## Commit & Pull Request Guidelines
- Match existing history: short, imperative, lower-case subjects (e.g., `add html report`).
- Detail behavior changes, manual run commands, and any updated screenshots or HTML diffs in the PR body.
- Link tracking issues and call out new environment variables or URL sources to aid reviewers.

## Observability & Configuration Tips
- Export `OPENAI_API_KEY` and any MCP tokens locally; never commit secrets or sample keys.
- Wrap new network operations in `async_tesla_operation_span` to keep traces consistent in logfire.
- Update the URL roster in `main.py` through helper functions where possible, maintaining comments for provenance.
