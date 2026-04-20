"""Parses the Shellcmd package under ``<installedpackages><shellcmdsettings>``.

Lets operators attach arbitrary shell commands to pfSense lifecycle
events (earlyshellcmd, shellcmd, afterfilterchangeshellcmd, ...).
The command strings themselves are not credentials, but they are
**operational footguns** — an operator changing an earlyshellcmd is
modifying what runs as root at boot. We surface them verbatim so the
diff view shows the full before/after; the raw-XML tab already
leaks the same content, so redacting here would just hide it.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class ShellCmdEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key for diffing — the actual stored type string
    # (``shellcmd``, ``earlyshellcmd``, ``afterfilterchangeshellcmd``).
    # ``cmd`` is the command line as stored verbatim.
    cmd: str
    cmdtype: str | None = None
    descr: str | None = None
    disabled: bool = False


class ShellCmdSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[ShellCmdEntry] = []


CONSUMED_TAGS = frozenset({"shellcmdsettings"})


def parse(ip: Element) -> ShellCmdSettings | None:
    el = ip.find("shellcmdsettings")
    if el is None:
        return None
    entries: list[ShellCmdEntry] = []
    # pfSense package config stores one or more ``<config>`` rows,
    # each carrying a single command. Older builds wrote ``<item>``.
    rows = children(el, "config")
    if not rows:
        rows = children(el, "item")
    for row in rows:
        cmd = text(row, "cmd") or text(row, "shellcmd")
        if not cmd:
            continue
        raw_type = text(row, "cmdtype") or text(row, "type")
        # pfSense's shellcmd package treats ``cmdtype="disabled"`` as
        # its own disable switch — parallel to (and distinct from) a
        # ``<disabled>on</disabled>`` child element. v0.17.0 read
        # cmdtype verbatim and surfaced ``disabled=False`` even when
        # the package had disabled the command via cmdtype, producing
        # a contradictory "type: disabled, disabled: no" row in the
        # viewer. Normalize: when cmdtype is ``"disabled"``, flip the
        # boolean and drop the type (there's no actual run phase to
        # name for a disabled entry).
        disabled = bool_flag(row, "disabled")
        cmdtype: str | None
        if raw_type == "disabled":
            disabled = True
            cmdtype = None
        else:
            cmdtype = raw_type
        entries.append(
            ShellCmdEntry(
                cmd=cmd,
                cmdtype=cmdtype,
                descr=text(row, "descr") or text(row, "description"),
                disabled=disabled,
            )
        )
    return ShellCmdSettings(entries=entries)
