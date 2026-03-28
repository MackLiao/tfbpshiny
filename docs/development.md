# Developer notes

`CLAUDE.md` is required reading for humans, also. It explains the structure of the
codebase and how to use it.

## Challenges

### DuckDB

For the correlations, there is some problem with cases where the stddev is 0 and
the correlation is undefined. This may or may not be relevant -- should be aware

https://github.com/duckdb/duckdb/issues/13763

see duckdb docs:

https://duckdb.org/docs/current/operations_manual/non-deterministic_behavior#floating-point-aggregate-operations-with-multi-threading

Do not want to set threads to 1 unless absolutely necessary.

### plotly

There have been challenges using plotly with shiny.

Currently, Plots are rendered as static HTML via ``plotly.io.to_html`` + ``ui.HTML``,
using ``@render.ui`` rather than ``render_widget`` / ``output_widget``
from shinywidgets.  

Current strategy is to use ``render_widget`` to wrap figures as ``FigureWidget``
(an ipywidget), which maintains a persistent comm channel between the Python
server and the browser. When the user navigates away from this module the DOM is
destroyed, tearing down the comm. On return, shinywidgets tries to re-attach the
old comm ID to the new DOM nodes and fails with a ``t.views is
undefined`` / ``[anywidget] Runtime not found`` client error.  

Using ``to_html`` produces a self-contained HTML+JS blob that is fully re-rendered by
the browser each time the ``@render.ui`` output updates, with no persistent state.
The resulting Plotly figures are still fully interactive client-side
(hover, zoom, pan). This also means that server-side callbacks on plot events are
not possible. And, it will be less efficient for large datasets and frequent
updates.  

For right now, this works. But if it gets prohibitively slow, or server-side
callbacks are necessary, then either a different plotting library or a custom
implementation of some sort will likely be necessary. Would be nice to explore
other options, including custom implementations of plots using d3 and then creating
the shiny widget manually. With AI, that might be more achievable (for me at least)
than it would be otherwise b/c we can give the AI the docs for all three as context.