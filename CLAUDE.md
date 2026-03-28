# TFBPShiny - Claude Development Guide

This document provides context for AI assistants working on the TFBPShiny project.

## Project Overview

TFBPShiny is a Shiny web application for exploring transcription factor binding and
perturbation data from the Brent Lab yeast collection. The application provides a
dashboard interface to visualize and analyze genomics data.

- **Main repository**: https://github.com/BrentLab/tfbpshiny
- **Data collection**: https://huggingface.co/collections/BrentLab/yeastresources
- **Production URL**: https://tfbindingandperturbation.com

## Reference Repositories

Two companion repositories are available as workspace folders and online. Use them
when working with Shiny components or labretriever data access — read their source rather
than guessing at APIs.

| Package | Local path | Online source |
|---------|-----------|---------------|
| py-shiny (Shiny for Python source) | `@py-shiny-site (reference)` | https://github.com/posit-dev/py-shiny |
| labretriever | `@labretriever (reference)` | https://github.com/cmatKhan/labretriever |
| duckDB (for SQL query reference) | `@duckdb (reference)` | https://duckdb.org/docs/stable/
| plotly | `@plotly (reference)`   | https://plotly.com/python/ |
| terraform | `@terraform (reference)` | https://developer.hashicorp.com/terraform/docs

## Technology Stack

### Shiny Framework

**IMPORTANT**: This application uses **Shiny Core** (NOT Shiny Express).

- **Official API reference**: https://shiny.posit.co/py/api/core/
- **Shiny for Python docs**: https://shiny.posit.co/py/docs/
- Always verify component signatures against the Shiny Core API — do not infer from
  Express examples or older shinysession patterns
- Version: ^1.4.0 (see pyproject.toml for exact version)

### labretriever Library

The application uses `labretriever` for data access and manipulation. It is installed from
the github branch via Poetry. When in doubt about available methods or data structures,
read the source in `@labretriever (reference)` or check https://brentlab.github.io/labretriever/.

### Other Key Dependencies

- **Python**: ^3.11
- **Plotly**: ^6.0.1 (for visualizations)
- **shinywidgets**: ^0.5.2
- **python-dotenv**: ^1.1.0 (environment configuration)
- **faicons**: ^0.2.2 (icons)

## Application Architecture

### Module-Based Structure

```
tfbpshiny/
├── app.py              # Main application shell and orchestration
├── app.css             # Global styles and CSS custom properties
├── components.py       # Reusable styled UI component library (see below)
├── modules/            # Feature modules
│   ├── home/           # The home page module (splash screen)
│   ├── binding/        # TF binding data module
│   ├── perturbation/   # Perturbation data module
│   ├── comparison/     # Comparison analysis module
│   └── select_datasets/# Dataset selection module
└── utils/              # Shared utilities
```

### Module Pattern

Each module follows a consistent structure:
- `ui.py` — UI component definitions (sidebar and workspace)
- `server/sidebar.py` — Sidebar server logic
- `server/workspace.py` — Workspace server logic
- `page_test.py` - This is a standalone Shiny app for testing the module in
  isolation during development. It should not be imported or referenced in
  the main app. It should set up mock data to pass as input to the module's
  server functions and render the UI components. As the testing framework
  is implemented and developed, this may become optional or be removed.
  However, currently it is required.
- `queries.py` (optional) — If needed, SQL query templates used in the module against
  `vdb`. **Note**: queries.py is excluded from flake8 linting due to the presence of
  long SQL query strings that may exceed typical line length limits. This allows for
  better readability of SQL queries without triggering linting errors.
  **Convention**: any function in `queries.py` that executes SQL against `vdb` directly
  (i.e. calls `vdb.query()` internally) must accept a `sql_only: bool = False` keyword
  argument. When `sql_only=True` the function returns a `(sql_string, params_dict)`
  tuple instead of executing the query. This is useful for debugging and
  notebook-based investigation.

### Styled Component Library (`components.py`)

`tfbpshiny/components.py` is the **single source of truth** for all reusable,
styled Shiny UI elements.  Every function maps to one or more CSS classes defined in
`app.css` and documents that mapping in its docstring.

**When to use it:**
- Any time you build a sidebar shell, workspace shell, nav button, group header, dataset
  row, filter card, empty state, or matrix cell button — use the corresponding function
  from `components.py` rather than inlining the class string.
- When adding a new CSS class that will be used in more than one place, add a matching
  factory function to `components.py` at the same time.

**When to update it:**
- A CSS class in `app.css` is renamed → update the matching component function.
- A component's HTML structure changes (e.g. a new wrapper div) → update the function.
- A new globally reusable UI pattern appears in two or more module `ui.py` files →
  extract it into `components.py`.

**Rules:**
- No business logic or reactive code belongs here — only pure `ui.Tag` factories.
- Module `ui.py` files import from `components` (not from each other).
- `app.py` imports `github_badge` and `nav_button` from `components`.
- Do **not** inline `class_="nav-btn"`, `class_="empty-state"`, etc. anywhere else in
  the app — always go through `components.py`.

**Notable exception:** `select_datasets/ui.py` builds filter-option cards directly
because it injects a conditional "Apply to all datasets" toggle into the card header,
which the generic `filter_option_card()` component does not support.  The function
contains a comment explaining this.

### Layout System

The app uses a two-region layout:
1. **Sidebar region** — Dynamic content based on active module
2. **Workspace region** — Main content area for visualizations and data

`app.py` orchestrates overall application flow and state. Individual modules own their
UI and server logic. Navigation uses a top navbar with action buttons.

### Data Access

`VirtualDB` (`vdb`) is initialized once in `app.py` from `brentlab_yeast_collection.yaml`
and passed to modules as needed. Supports both local development and Docker deployment.

## Common Patterns

### Adding a New Module

1. Create module directory under `tfbpshiny/modules/`
2. Implement `ui.py` with `{module}_sidebar_ui()` and `{module}_workspace_ui()`
3. Implement `server/sidebar.py` with `{module}_sidebar_server()`
4. Implement `server/workspace.py` with `{module}_workspace_server()`
5. In `app.py`: add imports, navbar button, cases in `sidebar_region()` and
   `workspace_region()`, reactive effect for navigation, and module server calls

### Working with VirtualDB

Use the `vdb` instance to access data sources. Refer to the labretriever docs or
`@labretriever (reference)` source for available methods and data structures.

## Development Commands

```bash
# Install dependencies
poetry install

# Run the application (development)
poetry run python -m tfbpshiny --log-level DEBUG shiny \
    --port 8010 --host 127.0.0.1 --debug

# Code quality
poetry run black .
poetry run isort .
poetry run mypy .

# Testing
poetry run pytest tests/unit/          # unit tests only
poetry run pytest tests/e2e/           # end-to-end tests only
poetry run pytest                       # all tests

# Install Playwright browsers (first time only, required for E2E)
poetry run playwright install chromium
```

After making changes, verify by running the app and checking for import errors or
reactive warnings in the console output. Run unit tests after any change to server
logic; run E2E tests when changing navigation, module wiring, or UI interactions.

## Testing

This project uses pytest for both unit and end-to-end testing. Follow Shiny's
official testing guidelines.

- **Unit testing docs**: https://shiny.posit.co/py/docs/unit-testing.html
- **E2E testing docs**: https://shiny.posit.co/py/docs/end-to-end-testing.html

### Test Organization

```
tests/
├── unit/                       # Pure-function unit tests (no reactive context)
│   └── test_select_datasets.py # _build_where, query builders, ID generators
└── e2e/                        # Playwright end-to-end tests
    └── test_navigation.py      # Navigation smoke tests
```

### Unit Testing

Shiny for Python has no API for testing reactive server logic in isolation — there is
no `create_session` equivalent. Unit tests are limited to **pure Python functions**
that have been extracted from server code (e.g. query builders, ID generators,
data-transformation helpers). Test those with plain pytest; do not attempt to test
reactive effects or renders in unit tests.

Key patterns: test pure helper functions directly; mock external dependencies
(VirtualDB) with simple stubs when needed.

### End-to-End Testing

E2E tests use Playwright to verify full application flow as a user would experience
it. Use sparingly — cover critical workflows (navigation, module switching, modal
interactions, data selection) rather than exhaustive UI states.

```python
from playwright.sync_api import Page, expect
from shiny.pytest import create_app_fixture

app = create_app_fixture("path/to/app.py")

def test_navigation(page: Page, app):
    page.goto(app.url)
    page.click("#selection")
    expect(page.locator(".sidebar")).to_be_visible()
```

### Testing Best Practices

- Each test must be independent — no shared mutable state between tests
- Use fixtures for common setup (VirtualDB mocks, sample data)
- Mock all external dependencies in unit tests
- E2E tests should mirror real user workflows, not implementation details
- Include edge cases: empty data, error states, boundary conditions

## Code Style

- **Formatter**: Black (line-length: 88)
- **Import sorting**: isort (black profile)
- **Type checking**: mypy — use type annotations where possible (Python 3.11+)
- **Testing**: pytest with `shiny.pytest` (unit) and Playwright (E2E) — see Testing section below
- **Docstrings**: Sphinx style. Document parameters and return values; do not repeat
  types (those go in type hints). Inline comments above the line, not beside it.
  For `@reactive.calc` and `@reactive.event` functions, document what triggers
  re-computation using a `:trigger:` field:

  ```python
  @reactive.calc
  def _pairs() -> list[tuple[str, str]]:
      """
      All unique pairs of active binding datasets.

      :trigger: ``active_binding_datasets`` — re-runs whenever the selected
          datasets change.
      :returns: List of ``(db_a, db_b)`` tuples, length = n choose 2.
      """
  ```

  Use `:trigger:` for `@reactive.calc` (what reactive inputs/values it depends on)
  and for `@reactive.effect @reactive.event(...)` (what event fires it).
- **Pre-commit hooks**: run `pre-commit install` once after cloning

## Environment Configuration

A `.env` file in the root directory can override the VirtualDB configuration or set
a HuggingFace token for private repo access. See `python-dotenv` docs for format.

## Logging

- Logger name: `"shiny"`
- Configured via `configure_logger()` from the `configure_logger` module
- Controlled via environment variables:
  - `TFBPSHINY_LOG_LEVEL` (default: 10 = DEBUG)
  - `TFBPSHINY_LOG_HANDLER` (default: "console")

## Docker Deployment

Production uses Docker Compose (`production.yml`). Environment files in
`.envs/.production/`. Traefik handles reverse proxy routing.

The shinyapp service mounts a named Docker volume `hf_cache` at `/hf-cache`
inside the container, and sets `HF_HOME=/hf-cache`. This causes HuggingFace
downloads to land on the persistent volume rather than the container layer,
so the cache survives container rebuilds.

## Terraform / Infrastructure as Code

The `terraform/` directory contains Terraform configuration for provisioning
the EC2 instance on AWS. It manages:

- EC2 instance (Amazon Linux 2023, default `t3.small`, 20 GB gp3 root volume)
- Security group (ports 22, 80, 443)
- IAM role with `CloudWatchAgentServerPolicy` (required for the `awslogs` Docker log driver)
- `user_data.sh` cloud-init script that installs Docker + Compose plugin and clones the repo

It does **not** manage DNS records, SSL certificates (handled by Traefik/Let's Encrypt),
or secret env files (must be copied to the instance manually after provisioning).

**Key files:**
- `terraform/main.tf` — resource definitions and `public_ip` output
- `terraform/variables.tf` — `aws_region`, `instance_type`, `key_name`, `root_volume_gb`
- `terraform/terraform.tfvars.example` — copy to `terraform.tfvars` (gitignored) and fill in values
- `terraform/user_data.sh` — cloud-init script run on first boot

**Terraform state files and `terraform.tfvars` are gitignored.** Never commit them.

## Branch Strategy

- `main` — stable, production-ready
- `dev` — active development
- Feature branches from `dev` with descriptive names; keep up to date by rebasing

To contribute: open an issue, fork the repo, branch from `dev`, open a PR to `dev`
when complete.

## Important Notes / Common Mistakes

1. **Always use Shiny Core syntax** — not Express. If unsure, check
   https://shiny.posit.co/py/api/core/ or `@py-shiny-site (reference)`.
2. **Do not guess at labretriever APIs** — read the source in `@labretriever (reference)` or
   the docs at https://brentlab.github.io/labretriever/.
3. **Module isolation** — keep modules self-contained with clear interfaces.
4. **Reactive patterns** — follow Shiny's reactive programming model; avoid
   side effects outside reactive contexts.
5. **vdb is a singleton** — initialized once in `app.py`, passed to modules as an
   argument; do not re-instantiate it inside modules.
6. **Mock vdb in tests** — never hit real data sources in unit tests; create a mock
   VirtualDB fixture instead.
7. **E2E tests should be high-level** — test user workflows, not implementation details
  or extensively test internal state irrelevant to the specific user workflow being
  tested.
