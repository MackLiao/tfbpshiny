"""
Styled UI component library for TFBPShiny.

This module is the single source of truth for all reusable, styled Shiny UI
elements.  Every component here maps to one or more CSS classes in ``app.css``
and the mapping is documented in the function's docstring.

Purpose
-------
When the application logic is stable and it is time to focus on appearance,
changes to visual design should be made here (or in ``app.css``) rather than
scattered across individual module ``ui.py`` files.  Keeping structure and
styling in one place means:

  - A class rename in ``app.css`` requires only one call-site change here.
  - New structural variants (e.g. a compact sidebar row) can be added as
    keyword arguments without touching caller code.
  - The component list serves as living documentation of which CSS classes are
    in active use.

Maintenance rules
-----------------
- **Add a component** whenever a new CSS class is introduced in ``app.css`` and
  used in more than one place in the app.
- **Update a component** whenever its underlying CSS class is renamed or its
  structural HTML changes (e.g. a new wrapper div is added).
- **Do not** put business logic or reactive code here — components are pure
  ``ui.Tag`` factories.
- Components that require a Shiny ``id`` accept it as the first positional
  argument; purely structural wrappers use ``*children``.

CSS variable reference (from ``app.css`` ``:root``)
----------------------------------------------------
--color-primary        #2C7A7B
--color-primary-light  #E6FFFA
--color-primary-dark   #1A5456
--color-accent         #38B2AC
--color-bg             #F7FAFC
--color-surface        #FFFFFF
--color-border         #E2E8F0
--color-text           #1A202C
--color-text-muted     #718096
--color-text-light     #A0AEC0
--radius-sm            6px
--radius-md            10px
--shadow-sm            0 1px 3px rgba(0,0,0,.08)
--nav-height           52px
--sidebar-width        380px
--sidebar-font-size    0.8125rem   (rescales all sidebar text at once)
--transition-fast      150ms ease

"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from shiny import ui

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

try:
    _version = version("tfbpshiny")
except PackageNotFoundError:
    _version = "dev"

_GITHUB_URL = "https://github.com/BrentLab/tfbpshiny"

_GITHUB_SVG_PATH = (
    "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 "
    "7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-"
    "2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 "
    "1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-"
    "1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-"
    "1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 "
    "1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56"
    ".82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 "
    "0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 "
    "8c0-4.42-3.58-8-8-8z"
)


# ---------------------------------------------------------------------------
# Layout shells
# ---------------------------------------------------------------------------


def sidebar_shell(
    id: str,
    *,
    header: ui.Tag | str,
    body: ui.Tag,
    footer: ui.Tag | None = None,
) -> ui.Tag:
    """
    Full sidebar chrome: sticky header, scrollable body, optional footer.

    CSS: ``.context-sidebar``, ``.sidebar-header``, ``.sidebar-body``,
    ``.sidebar-footer``

    .. note::
        The Select Datasets sidebar uses ``context-sidebar selection-sidebar``
        and ``sidebar-header-row`` CSS modifiers that are not factored into
        component functions here. Those classes appear only once, in
        ``select_datasets/server/sidebar.py``, and carry collapsed-state
        conditional logic that makes a generic factory impractical.
    """
    children: list[Any] = [
        ui.div({"class": "sidebar-header"}, header),
        ui.div({"class": "sidebar-body"}, body),
    ]
    if footer is not None:
        children.append(ui.div({"class": "sidebar-footer"}, footer))
    return ui.div({"class": "context-sidebar", "id": id}, *children)


def workspace_shell(id: str, *, header: ui.Tag | str, body: ui.Tag) -> ui.Tag:
    """
    Full workspace chrome: fixed header bar, scrollable body.

    CSS: ``.main-workspace``, ``.workspace-header``, ``.workspace-body``
    """
    return ui.div(
        {"class": "main-workspace", "id": id},
        ui.div({"class": "workspace-header"}, header),
        ui.div({"class": "workspace-body"}, body),
    )


# ---------------------------------------------------------------------------
# Sidebar typography
# ---------------------------------------------------------------------------


def sidebar_heading(text: str) -> ui.Tag:
    """
    Primary sidebar section title (``h2``-level, 16 px, 600 weight).

    CSS: ``.sidebar-header h2``

    """
    return ui.h2(text)


def sidebar_subtitle(text: str) -> ui.Tag:
    """
    Muted sub-line beneath a sidebar heading (12 px, ``--color-text-muted``).

    CSS: ``.sidebar-header .subtitle``

    """
    return ui.div({"class": "subtitle"}, text)


def sidebar_section(title: str, *children: Any) -> ui.Tag:
    """
    Wrapper div that groups related sidebar controls under a labelled heading.

    CSS: ``.sidebar-section``, ``.sidebar-section-title``

    :param title: Short label rendered above the controls (e.g. ``"Column"``).
    :param children: One or more Shiny input elements placed below the title.

    """
    return ui.div(
        {"class": "sidebar-section"},
        ui.div({"class": "sidebar-section-title"}, title),
        *children,
    )


def group_header(text: str) -> ui.Tag:
    """
    All-caps section divider label inside a sidebar or workspace body (11 px, 700
    weight, ``--color-text-muted``).

    CSS: ``.group-header``

    """
    return ui.div({"class": "group-header"}, text)


def sidebar_text(*children: Any) -> ui.Tag:
    """
    Body text sized to ``--sidebar-font-size`` (default 0.8125 rem). Adjust the CSS
    variable in ``:root`` to rescale all sidebar text at once.

    CSS: ``.selection-sidebar .sidebar-text``

    """
    return ui.span({"class": "sidebar-text"}, *children)


# ---------------------------------------------------------------------------
# Workspace typography
# ---------------------------------------------------------------------------


def workspace_heading(text: str) -> ui.Tag:
    """
    Primary workspace page title (``h1``-level, 20 px, 600 weight).

    CSS: ``.workspace-header h1``

    """
    return ui.h1(text)


# ---------------------------------------------------------------------------
# Empty / placeholder states
# ---------------------------------------------------------------------------


def empty_state(*children: Any, compact: bool = False) -> ui.Tag:
    """
    Centred placeholder shown when there is nothing to display yet.

    CSS: ``.empty-state`` / ``.empty-state.compact``

    :param compact: Use reduced vertical padding (20 px vs 64 px) for inline
        placeholders inside a partially-populated workspace.

    """
    cls = "empty-state compact" if compact else "empty-state"
    return ui.div({"class": cls}, *children)


# ---------------------------------------------------------------------------
# Nav bar
# ---------------------------------------------------------------------------


def nav_button(id: str, label: str, *, active: bool = False) -> ui.Tag:
    """
    Pill-shaped navigation button in the top nav bar.

    CSS: ``.nav-bar .nav-btn`` / ``.nav-bar .nav-btn.active``

    Active state is applied at render time; the server is responsible for
    toggling the ``active`` class dynamically via JavaScript.

    :param active: Render with ``.active`` class (primary background, white text).

    """
    cls = "nav-btn active" if active else "nav-btn"
    return ui.input_action_button(id, label, class_=cls)


def github_badge() -> ui.Tag:
    """
    GitHub repo link with version pill, displayed at the right end of the nav bar.

    CSS: ``.github-badge``, ``.github-badge-version``

    """
    return ui.a(
        {"class": "github-badge", "href": _GITHUB_URL, "target": "_blank"},
        ui.tags.svg(
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "width": "16",
                "height": "16",
                "viewBox": "0 0 16 16",
                "fill": "currentColor",
                "style": "vertical-align:middle; margin-right:5px;",
            },
            ui.Tag("path", d=_GITHUB_SVG_PATH),
        ),
        ui.tags.span(
            {"style": "vertical-align:middle; margin-right:6px;"},
            "BrentLab/tfbpshiny",
        ),
        ui.tags.span({"class": "github-badge-version"}, f"v{_version}"),
    )


# ---------------------------------------------------------------------------
# Dataset selection row (Select Datasets sidebar)
# ---------------------------------------------------------------------------


def dataset_row(toggle: ui.Tag, label: str, filter_button: ui.Tag) -> ui.Tag:
    """
    Single dataset row: toggle switch + display name + filter button on one line.

    CSS: ``.dataset-row``, ``.dataset-row-label``, ``.dataset-item``

    :param toggle: A fully-constructed ``ui.input_switch`` element.
    :param label: Human-readable dataset display name.
    :param filter_button: A fully-constructed ``ui.input_action_button`` element
        (use :func:`filter_button` to build it).
    """
    return ui.div(
        {"class": "dataset-row dataset-item"},
        toggle,
        ui.span({"class": "dataset-row-label sidebar-text"}, label),
        filter_button,
    )


def dataset_list(*rows: ui.Tag) -> ui.Tag:
    """
    Vertical stack of ``dataset_row`` elements with a small gap between them.

    CSS: ``.dataset-list``

    """
    return ui.div({"class": "dataset-list"}, *rows)


def filter_button(id: str) -> ui.Tag:
    """
    Small "Filter" button at the right of each dataset row.

    CSS: ``.btn-filter-dataset``

    """
    return ui.input_action_button(
        id,
        "Filter",
        class_="btn btn-sm btn-outline-secondary btn-filter-dataset",
    )


def collapse_sidebar_button(id: str, icon: ui.Tag) -> ui.Tag:
    """
    Square icon button used to collapse/expand the selection sidebar.

    CSS: ``.btn-collapse-sidebar``

    """
    return ui.input_action_button(id, icon, class_="btn-collapse-sidebar")


# ---------------------------------------------------------------------------
# Filter modal building blocks
# ---------------------------------------------------------------------------


def filter_option_card(title: str, *controls: ui.Tag) -> ui.Tag:
    """
    Bordered card containing a single filter control (slider, selectize, switch).

    CSS: ``.filter-option-card``, ``.filter-option-header``, ``.filter-option-title``

    :param title: Field name shown in bold at the top of the card.
    :param controls: One or more Shiny input elements placed below the header.

    """
    return ui.div(
        {"class": "filter-option-card"},
        ui.div(
            {"class": "filter-option-header"},
            ui.span({"class": "filter-option-title"}, title),
        ),
        *controls,
    )


def modal_section(*cards: ui.Tag) -> ui.Tag:
    """
    Vertical stack of ``filter_option_card`` elements inside a modal column.

    CSS: ``.modal-section``

    """
    return ui.div({"class": "modal-section"}, *cards)


# ---------------------------------------------------------------------------
# Intersection matrix table
# ---------------------------------------------------------------------------


def matrix_cell_button(id: str, label: str, *, tooltip: str | None = None) -> ui.Tag:
    """
    Full-width, borderless Shiny action button that fills a matrix table cell.

    CSS: ``.matrix-cell-button``

    :param id: Shiny input ID for the button (e.g. ``"diag_harbison"``).
    :param label: Text displayed inside the button.
    :param tooltip: When provided, sets the native ``title`` attribute so browsers
        show a hover tooltip.

    """
    attrs: dict[str, str] = {"class": "matrix-cell-button"}
    if tooltip is not None:
        attrs["title"] = tooltip
    return ui.input_action_button(id, label, **attrs)


def matrix_header_cell(label: str, *, row: bool = False) -> ui.Tag:
    """
    Header cell (``<th>``) for the intersection matrix.

    CSS:

    - ``row=False`` (default) — column header: ``.matrix-col-header``,
      ``.matrix-header-name``. Used for each dataset column in the top row.
    - ``row=True`` — row header: ``.matrix-row-header``. Used for the first
      ``<th>`` in the header row (typically labelled ``"Dataset"``).

    :param label: Text shown in the header cell.
    :param row: When ``True``, renders as a row header rather than a column header.

    """
    if row:
        return ui.tags.th({"class": "matrix-row-header"}, label)
    return ui.tags.th(
        {"class": "matrix-col-header"},
        ui.div({"class": "matrix-header-name"}, label),
    )


def matrix_row_label(label: str) -> ui.Tag:
    """
    Row label cell (``<td>``) showing the dataset name at the start of each row.

    CSS: ``.matrix-row-label``

    :param label: Dataset display name.

    """
    return ui.tags.td({"class": "matrix-row-label"}, label)


def matrix_cell(
    kind: Literal["empty", "diagonal", "interactive"],
    button: ui.Tag | None = None,
    *,
    active: bool = False,
) -> ui.Tag:
    """
    Data cell (``<td>``) in the intersection matrix.

    CSS by ``kind``:

    - ``"empty"`` — lower-triangle placeholder: ``.matrix-cell-empty``.
      No button; ``button`` argument is ignored.
    - ``"diagonal"`` — on-diagonal cell showing regulator/sample counts for one
      dataset: ``.matrix-cell-diagonal``. Wraps a ``matrix_cell_button``.
    - ``"interactive"`` — upper-triangle cell showing the common-regulator count
      for a dataset pair: ``.matrix-cell-interactive``. Wraps a
      ``matrix_cell_button``. When ``active=True`` also adds
      ``.matrix-cell-active`` to highlight the pair whose intersection is the
      current regulator filter.

    :param kind: One of ``"empty"``, ``"diagonal"``, or ``"interactive"``.
    :param button: A ``matrix_cell_button`` element. Required for ``"diagonal"``
        and ``"interactive"``; ignored for ``"empty"``.
    :param active: Only relevant for ``kind="interactive"``. Adds
        ``.matrix-cell-active`` when ``True``.

    """
    if kind == "empty":
        return ui.tags.td({"class": "matrix-cell-empty"}, "")
    if kind == "diagonal":
        return ui.tags.td({"class": "matrix-cell-diagonal"}, button)
    # interactive
    cls = (
        "matrix-cell-interactive matrix-cell-active"
        if active
        else "matrix-cell-interactive"
    )
    return ui.tags.td({"class": cls}, button)


def matrix_table(header_row: ui.Tag, *body_rows: ui.Tag) -> ui.Tag:
    """
    Full intersection matrix ``<table>``.

    CSS: ``.matrix-summary-table``

    :param header_row: A ``<tr>`` built from ``matrix_row_header`` and
        ``matrix_col_header`` cells.
    :param body_rows: One ``<tr>`` per active dataset, built from
        ``matrix_row_label``, ``matrix_cell_empty``, ``matrix_cell_diagonal``,
        and ``matrix_cell_interactive`` cells.

    """
    return ui.tags.table(
        {"class": "matrix-summary-table"},
        ui.tags.thead(header_row),
        ui.tags.tbody(*body_rows),
    )


__all__ = [
    # layout
    "sidebar_shell",
    "workspace_shell",
    # sidebar typography
    "sidebar_heading",
    "sidebar_subtitle",
    "sidebar_section",
    "group_header",
    "sidebar_text",
    # workspace typography
    "workspace_heading",
    # states
    "empty_state",
    # nav
    "nav_button",
    "github_badge",
    # dataset selection
    "dataset_row",
    "dataset_list",
    "filter_button",
    "collapse_sidebar_button",
    # filter modal
    "filter_option_card",
    "modal_section",
    # matrix
    "matrix_cell_button",
    "matrix_header_cell",
    "matrix_row_label",
    "matrix_cell",
    "matrix_table",
]
