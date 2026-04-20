"""Per-package parsers for pfSense's ``<installedpackages>`` section.

Each supported package gets its own module with a ``parse(el: Element) ->
PackageResult`` function, where ``el`` is the ``<installedpackages>``
node itself. That wider scope (vs. per-tag) matters because most
packages sprinkle their config across multiple sibling tags
(``pfblockerngipsettings``, ``pfblockerngdnsblsettings``, …). The
parser pulls the set it claims and reports the tags it consumed so
the dispatcher can expose the rest as unknown.

Unknown / out-of-scope packages flow into ``UnknownPackage`` with the
raw XML preserved for the UI fallback renderer — same pattern as
``unrecognized_sections`` at the top level.
"""
