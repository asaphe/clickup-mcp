# Contributing to ClickUp MCP Server

Thank you for considering a contribution. This server connects Claude to ClickUp via the Model Context Protocol.

## How to Contribute

### Reporting Issues

Open an issue describing:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Python version, uv version, Claude Code/Desktop version)

### Submitting Changes

1. Fork the repository
2. Create a branch: `fix/short-description` or `feat/short-description`
3. Make your changes
4. Run the quality checks (see below)
5. Submit a pull request

### Quality Checks

```bash
uv sync --dev
uv run pytest
uv run mypy clickup_mcp_server
uv run ruff check .
uv run ruff format --check .
```

All checks must pass before submitting a PR.

### What Makes a Good Contribution

- **Bug fixes with reproduction steps** — describe what broke and how to verify the fix
- **New tools** — follow the existing pattern in `clickup_mcp_server/tools/`. Each tool needs a docstring that serves as the MCP tool description
- **Setup improvements** — the setup experience (`setup_mcp.py`) should work on first try for macOS, Linux, and Windows
- **Test coverage** — new tools should include tests

### What to Avoid

- PII, company-specific details, workspace IDs, or API tokens in any form (code, comments, tests, docs)
- Breaking changes to existing tool signatures without a migration path
- Dependencies that don't work cross-platform (macOS, Linux, Windows)

## Code Style

- Python 3.12+ with type annotations
- `ruff` for linting and formatting
- `mypy` for type checking (strict mode)
- Pydantic for API models
- Google-style docstrings where non-obvious

## Architecture

New tools go in `clickup_mcp_server/tools/` and are registered in `server.py`. The client (`client.py`) handles HTTP, retries, and rate limiting — tools should use it rather than making direct HTTP calls.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
