# Reactivity & Dataflow Documentation

This document maps the reactive dataflow of the tfbpshiny Shiny application
for developer reference during further development.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Shared Reactive State](#shared-reactive-state)
3. [Core Dataflow Pipelines](#core-dataflow-pipelines)
4. [Inter-Module Communication](#inter-module-communication)
5. [Reactive Computations](#reactive-computations)
6. [Reactive Effects](#reactive-effects)
7. [Render Outputs](#render-outputs)
8. [File Reference](#file-reference)

---

## High-Level Architecture

The app has two major phases controlled by `active_module`:

```
              active_module
                   |
        +----------+----------+
        |                     |
   "selection"         "binding" / "perturbation" / "composite"
        |                     |
   Selection Phase       Analysis Phase
   (sidebar + matrix)   (sidebar + workspace)
```

**Selection Phase** -- user picks datasets, applies per-dataset filters,
computes an intersection matrix, then clicks a cell to navigate into analysis.

**Analysis Phase** -- user views filtered data tables, correlation plots,
summary stats, or pairwise comparisons for the datasets selected earlier.

---

## Shared Reactive State

All top-level reactive values are defined in `app_server` (`app.py:108-148`)
and passed by reference to child modules. Any module can read or write them.

### Navigation & Module State

| Reactive Value | Type | Purpose |
|---|---|---|
| `active_module` | `str` | Current view: `"selection"`, `"binding"`, `"perturbation"`, `"composite"` |

### Dataset Management

| Reactive Value | Type | Purpose |
|---|---|---|
| `datasets` | `list[dict]` | All available datasets with `selected`, `tf_count`, metadata |
| `datasets_loading` | `bool` | Initial dataset fetch loading state |
| `datasets_error` | `str \| None` | Error from dataset fetch |

### Selection & Filtering

| Reactive Value | Type | Purpose |
|---|---|---|
| `logic_mode` | `str` | `"intersect"` (AND) or `"union"` (OR) |
| `dataset_filters` | `dict` | `{dataset_id: {categorical: {...}, numeric: {...}}}` |
| `filter_options_by_dataset` | `dict` | Cached metadata filter choices per dataset |
| `filter_options_loading_by_dataset` | `dict` | Loading state per dataset |

### Intersection

| Reactive Value | Type | Purpose |
|---|---|---|
| `intersection_cells` | `list` | Matrix of pairwise intersection counts |
| `has_loaded_intersection` | `bool` | Whether intersection has been computed at least once |
| `intersection_loading` | `bool` | Active computation loading state |
| `intersection_error` | `str \| None` | Error from intersection computation |
| `last_selection_signature` | `str` | JSON hash for change detection |

### Modal State

| Reactive Value | Type | Purpose |
|---|---|---|
| `active_config_dataset_id` | `str \| None` | Which dataset's filter config modal is open |
| `intersection_detail` | `dict \| None` | Payload for intersection detail modal |
| `latest_navigation_intent` | `dict \| None` | Navigation payload from detail modal |

### Analysis Configuration

| Reactive Value | Type | Purpose |
|---|---|---|
| `analysis_config` | `dict` | Controls analysis views (see below) |

`analysis_config` structure:

```python
{
    "view": "table" | "correlation" | "summary" | "compare",
    "selected_db_name": str,         # Dataset A
    "comparison_db_name": str,       # Dataset B (pairwise)
    "comparison_mode": bool,
    "p_value": float,
    "log2fc_threshold": float,
    "correlation_value_column": str,
    "correlation_group_by": str,
    "page": int,
    "page_size": int,
}
```

---

## Core Dataflow Pipelines

### Pipeline 1: Dataset Selection -> Intersection Matrix

```
User toggles dataset checkboxes (selection sidebar)
    |
    v
datasets.set(updated list)                          [selection_sidebar.py]
    |
    v
_selected_datasets()  (calc: filter selected=True)  [app.py]
    |
    v
_selected_filter_payloads()  (calc: structure filters by db_name)
    |
    v
_selection_signature()  (calc: JSON hash of selection + filters)
    |
    v
_reset_intersection_on_signature_change()  (effect)
    |-- intersection_cells.set([])
    |-- has_loaded_intersection.set(False)
    |-- Matrix displays "Click Refresh Matrix"
    |
    v
User clicks Refresh button
    |
    v
_handle_refresh_intersection()  (callback)
    |-- Calls API with selected datasets + filter payloads
    |-- intersection_cells.set(cells)
    |-- has_loaded_intersection.set(True)
    |
    v
matrix_content() re-renders                         [selection_matrix.py]
    |-- _cell_map(): {row::col -> count}
    |-- _diagonal_tf_map(): {db_name -> tf_count}
    |-- _max_off_diagonal(): max count for color scaling
    |-- Renders clickable heatmap cells
```

### Pipeline 2: Intersection Cell Click -> Pairwise Comparison

```
User clicks a matrix cell
    |
    v
_watch_cell_clicks() detects click increase          [selection_matrix.py]
    |
    v
on_cell_click(payload) callback -> app_server
    |
    v
intersection_detail.set({                            [app.py]
    rowDataset: {id, dbName, type, name, tfCount},
    colDataset: {id, dbName, type, name, tfCount},
    intersectionCount: count
})
    |
    v
modal_layer() renders IntersectionDetailModal
    |-- Shows row/col dataset info, common TF count, percentages
    |-- "Open in Analysis" button
    |
    v
User clicks "Open in Analysis"
    |
    v
_emit_navigation_intent_from_modal()                 [app.py]
    |-- resolve_analysis_module(rowType, colType) -> target module
    |-- analysis_config.set({
    |       selected_db_name: row db_name,
    |       comparison_db_name: col db_name,
    |       comparison_mode: True,
    |       view: "compare",
    |   })
    |-- active_module.set(target)
    |-- intersection_detail.set(None)
    |
    v
Analysis phase activates
    |-- sidebar_region() switches to analysis_sidebar_ui
    |-- workspace_region() switches to analysis_workspace_ui
    |-- Sidebar pre-fills with dataset A/B selections
    |-- Workspace renders pairwise comparison view
```

### Pipeline 3: Per-Dataset Filter -> Intersection Update

```
User clicks configure button on a dataset            [selection_sidebar.py]
    |
    v
_watch_configure_buttons() detects click
    |
    v
on_configure(dataset_id) callback -> app_server
    |
    v
_handle_open_config(dataset_id)                      [app.py]
    |-- active_config_dataset_id.set(dataset_id)
    |-- _ensure_dataset_filter_options(dataset_id)
    |   |-- Check cache in filter_options_by_dataset
    |   |-- If not cached: fetch options, store in cache
    |
    v
modal_layer() renders DatasetConfigModal
    |-- Categorical selectors (e.g. TF symbol, locus tag)
    |-- Numeric range inputs (e.g. p-value bounds)
    |-- Identifier mode toggles (symbol vs locus)
    |
    v
User adjusts filters, clicks "Apply Filters"
    |
    v
_apply_config_modal_filters()                        [app.py]
    |-- Collect all modal inputs
    |-- normalize_dataset_filters(): drop empties, convert types
    |-- enforce_identifier_groups(): resolve symbol/locus conflicts
    |-- dataset_filters.set({dataset_id: {categorical, numeric}})
    |-- active_config_dataset_id.set(None)  (close modal)
    |
    v
_selected_filter_payloads() recalculates             [app.py]
    |
    v
_selection_signature() changes
    |
    v
_reset_intersection_on_signature_change()
    |-- Clears intersection, shows "Click Refresh"
    |
    v
User clicks Refresh -> intersection recomputed with filters applied
    |
    v
matrix_content() re-renders with filtered counts
```

### Pipeline 4: Analysis Sidebar <-> Config Two-Way Sync

```
analysis_config changes (from navigation or user)
    |
    v
_sync_controls_from_config()                         [analysis_sidebar.py]
    |-- Updates UI controls to match config
    |
    v
User changes sidebar controls
    |
    v
_sync_config()                                       [analysis_sidebar.py]
    |-- Reads all control values
    |-- Validates constraints (datasets exist, no A==B, etc.)
    |-- analysis_config.set(updated)
    |
    v
workspace_content() re-renders                       [analysis_workspace.py]
    |-- Dispatches to _render_table(), _render_correlation(),
    |   _render_summary(), or _render_pairwise_compare()
```

---

## Inter-Module Communication

### Pattern: Shared Reactive Values by Reference

Modules receive reactive values as arguments and can both read and write them.
Changes are immediately visible to all consumers.

```python
# In app_server:
datasets = reactive.value([...])

# Passed to child module:
selection_sidebar_server(..., datasets=datasets, ...)

# Child can read:  datasets()
# Child can write: datasets.set(new_value)
# Triggers all dependents everywhere
```

### Pattern: Callbacks for Parent Orchestration

Child modules receive callback functions from the parent. When a child event
occurs, it calls the callback, and the parent handles the orchestration.

```python
# Parent defines:
def _handle_open_config(dataset_id: str): ...
def _handle_refresh_intersection(): ...

# Child receives:
selection_sidebar_server(
    ...,
    on_configure=_handle_open_config,
    on_refresh=_handle_refresh_intersection,
    on_clear_all_filters=_handle_clear_all_filters,
)

# Child invokes: on_configure(dataset_id)
```

### Callback Registry

| Callback | From Module | To (app_server) | Purpose |
|---|---|---|---|
| `on_configure(dataset_id)` | selection_sidebar | `_handle_open_config` | Open filter config modal |
| `on_refresh()` | selection_sidebar | `_handle_refresh_intersection` | Compute intersection matrix |
| `on_clear_all_filters()` | selection_sidebar | `_handle_clear_all_filters` | Clear all dataset filters |
| `on_cell_click(payload)` | selection_matrix | `_handle_matrix_cell_click` | Open intersection detail modal |

### Module-Level Reactive Values

| Module | Reactive Value | Purpose |
|---|---|---|
| `selection_sidebar` | `collapsed` | Sidebar collapse state |
| `selection_sidebar` | `configure_clicks` | Click counter for config buttons |
| `selection_matrix` | `cell_click_counts` | Click counter for matrix cells |

---

## Reactive Computations

All `@reactive.calc` functions (derived state):

| Calculation | File | Dependencies | Output |
|---|---|---|---|
| `_selected_datasets()` | app.py | `datasets` | Datasets where `selected=True` |
| `_selected_filter_payloads()` | app.py | `_selected_datasets`, `dataset_filters` | `{categorical: {db_name: ...}, numeric: {db_name: ...}}` |
| `_selection_signature()` | app.py | `_selected_datasets`, `_selected_filter_payloads` | JSON hash string for change detection |
| `_combined_selection_error()` | app.py | `datasets_error`, `intersection_error` | First non-null error |
| `_active_datasets()` | selection_matrix.py | `datasets` | Selected datasets only |
| `_cell_map()` | selection_matrix.py | `intersection_cells` | `{row::col -> count}` lookup |
| `_diagonal_tf_map()` | selection_matrix.py | `intersection_cells` | `{db_name -> tf_count}` |
| `_max_off_diagonal()` | selection_matrix.py | `_active_datasets`, `_cell_map` | Max off-diagonal count (for color scaling) |

---

## Reactive Effects

All `@reactive.effect` functions (side effects):

### Selection Phase

| Effect | File | Trigger | Action |
|---|---|---|---|
| `_reset_intersection_on_signature_change` | app.py | `_selection_signature` changes | Clear intersection data, set `has_loaded=False` |
| `_sync_logic_mode` | selection_sidebar.py | `input.logic_mode` | Update `logic_mode` reactive value |
| `_sync_dataset_toggles` | selection_sidebar.py | Dataset toggle inputs | Update `datasets` selected state |
| `_watch_configure_buttons` | selection_sidebar.py | Configure button clicks | Call `on_configure()` callback |
| `_refresh_matrix` | selection_sidebar.py | `input.refresh` click | Call `on_refresh()` callback |
| `_clear_all_filters` | selection_sidebar.py | `input.clear_all_filters` | Call `on_clear_all_filters()` callback |
| `_toggle_sidebar` | selection_sidebar.py | `input.toggle_sidebar` | Toggle `collapsed` state |
| `_watch_cell_clicks` | selection_matrix.py | Matrix cell button clicks | Call `on_cell_click()` callback |

### Modal Interactions

| Effect | File | Trigger | Action |
|---|---|---|---|
| `_sync_modal_include_toggle` | app.py | `input.modal_include_dataset` | Update dataset selected state from modal |
| `_close_config_modal_from_header` | app.py | `input.modal_close_config` | `active_config_dataset_id.set(None)` |
| `_close_config_modal_from_cancel` | app.py | `input.modal_cancel_filters` | `active_config_dataset_id.set(None)` |
| `_clear_config_modal_draft` | app.py | `input.modal_clear_filters` | Reset filter inputs to empty |
| `_apply_config_modal_filters` | app.py | `input.modal_apply_filters` | Commit filters to `dataset_filters`, close modal |
| `_close_intersection_modal_*` | app.py | Close buttons | `intersection_detail.set(None)` |
| `_emit_navigation_intent_from_modal` | app.py | `input.modal_open_analysis` | Build analysis config, switch module, close modal |

### Analysis Phase

| Effect | File | Trigger | Action |
|---|---|---|---|
| `_sync_controls_from_config` | analysis_sidebar.py | `active_module`, `analysis_config` | Update sidebar UI from config |
| `_update_dataset_choices` | analysis_sidebar.py | `active_module`, `datasets`, `analysis_config` | Populate dataset selectors |
| `_sync_config` | analysis_sidebar.py | All sidebar input controls | Write changes to `analysis_config` |
| `_swap_datasets` | analysis_sidebar.py | `input.swap_datasets` | Swap A/B datasets |
| `_exit_comparison` | analysis_sidebar.py | `input.exit_comparison` | Disable comparison mode |

### Navigation

| Effect | File | Trigger | Action |
|---|---|---|---|
| `_click_selection` | nav.py | `input.nav_selection` | `active_module.set("selection")` |
| `_click_binding` | nav.py | `input.nav_binding` | `active_module.set("binding")` |
| `_click_perturbation` | nav.py | `input.nav_perturbation` | `active_module.set("perturbation")` |
| `_click_composite` | nav.py | `input.nav_composite` | `active_module.set("composite")` |

---

## Render Outputs

All `@render.ui` functions:

| Render | File | Dependencies | Output |
|---|---|---|---|
| `sidebar_region` | app.py | `active_module` | Selection sidebar or analysis sidebar |
| `workspace_region` | app.py | `active_module` | Selection matrix or analysis workspace |
| `modal_layer` | app.py | `active_config_dataset_id`, `intersection_detail` | Config modal, detail modal, or nothing |
| `sidebar_panel` | selection_sidebar.py | `collapsed`, `datasets`, `logic_mode`, filters | Full sidebar UI with dataset list |
| `matrix_content` | selection_matrix.py | `_active_datasets`, `intersection_cells`, loading states | Heatmap matrix or loading/empty/error state |
| `nav_buttons` | nav.py | `active_module` | 4 nav buttons with active styling |
| `sidebar_title` | analysis_sidebar.py | `active_module`, `analysis_config` | Module label |
| `comparison_hint` | analysis_sidebar.py | `analysis_config` | Pairwise hint text |
| `workspace_title` | analysis_workspace.py | `active_module`, `analysis_config` | View heading |
| `workspace_content` | analysis_workspace.py | `analysis_config`, `active_module`, `datasets` | Table / correlation / summary / pairwise view |

---

## File Reference

| Component | File | Key Lines |
|---|---|---|
| App orchestration & reactive values | `tfbpshiny/app.py` | 100-637 |
| Selection sidebar module | `tfbpshiny/modules/selection_sidebar.py` | 22-395 |
| Selection matrix module | `tfbpshiny/modules/selection_matrix.py` | 28-324 |
| Analysis sidebar module | `tfbpshiny/modules/analysis_sidebar.py` | 153-384 |
| Analysis workspace module | `tfbpshiny/modules/analysis_workspace.py` | 40-156 |
| Navigation module | `tfbpshiny/modules/nav.py` | 28-81 |
| Modal builders & filter helpers | `tfbpshiny/modules/modals.py` | 42-559 |

---

## Summary of Reactive Patterns Used

| Pattern | Example | Location |
|---|---|---|
| Derived state | `_selected_datasets()` filters `datasets` | `@reactive.calc` |
| Change detection via signature | `_selection_signature()` -> reset effect | app.py |
| Event-driven effects | `_apply_config_modal_filters()` on button click | `@reactive.event` |
| Click counting | `cell_click_counts` detects increases | selection_matrix.py |
| Callbacks to parent | `on_configure(dataset_id)` | selection_sidebar.py -> app.py |
| Conditional modal overlay | `modal_layer()` switches on active modal state | app.py |
| Two-way sync | Sidebar controls <-> `analysis_config` | analysis_sidebar.py |
| Chained filter pipeline | `dataset_filters` -> payloads -> signature -> reset | app.py |
| Module routing | `active_module` -> conditional `@render.ui` | app.py |
