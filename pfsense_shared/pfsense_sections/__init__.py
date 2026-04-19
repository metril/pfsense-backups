"""Per-section parsers for pfSense config.xml.

Each module in this package owns one (or a small related group) of
top-level ``config.xml`` tags. Modules expose a single public ``parse``
function that takes the root ``<pfsense>`` element and returns a
Pydantic model (or list of models) describing that section.

Section parsers are deliberately tolerant: missing fields become
``None`` or ``[]`` rather than raising. pfSense's schema drifts across
versions and we'd rather render a partial config than bail on the
whole backup because one optional tag vanished.
"""
