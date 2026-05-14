#!/usr/bin/env python3
"""cronmgr – Cron Job Manager  ·  Windows 11-style TUI + CLI.

Python ≥ 3.10 required (match statement, X|Y type hints).
"""

import argparse
import curses
import datetime
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CronEntry:
    index: int      # 1-based line number in the full raw crontab
    raw: str        # original text line (preserved for save round-trips)
    is_job: bool    # False for blank / comment-only lines
    schedule: str = ""
    command: str = ""
    comment: str = ""

    def __str__(self) -> str:
        tag = f"  # {self.comment}" if self.comment else ""
        return f"{self.schedule}  {self.command}{tag}" if self.is_job else self.raw

# ══════════════════════════════════════════════════════════════════════════════
# Crontab I/O
# ══════════════════════════════════════════════════════════════════════════════

CRON_RE = re.compile(
    r"^(\S+(?:\s+\S+){4}|@\w+)\s+([^#]+?)\s*(?:#\s*(.*))?$"
)

def _run(args: list[str], input_data: str | None = None) -> str:
    result = subprocess.run(args, input=input_data, capture_output=True, text=True)
    if result.returncode not in (0, 1):   # crontab -l exits 1 on empty crontab
        raise RuntimeError(result.stderr.strip() or f"crontab exited {result.returncode}")
    return result.stdout

def _cmd(user: str | None) -> list[str]:
    return ["crontab", "-u", user] if user else ["crontab"]

def load_entries(user: str | None) -> list[CronEntry]:
    raw = _run([*_cmd(user), "-l"])
    entries: list[CronEntry] = []
    for idx, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        m = CRON_RE.match(stripped)
        if m and not stripped.startswith("#"):
            entries.append(CronEntry(
                index=idx, raw=line, is_job=True,
                schedule=m.group(1),
                command=m.group(2).strip(),
                comment=(m.group(3) or "").strip(),
            ))
        else:
            entries.append(CronEntry(index=idx, raw=line, is_job=False))
    return entries

def save_entries(entries: list[CronEntry], user: str | None) -> None:
    content = "\n".join(e.raw for e in entries) + "\n"
    _run([*_cmd(user), "-"], input_data=content)

# ══════════════════════════════════════════════════════════════════════════════
# Color system  (Windows 11 Fluent Design approximation)
# ══════════════════════════════════════════════════════════════════════════════

_CP_TITLEBAR = 1   # title bar                 white / blue
_CP_BORDER   = 2   # box borders               cyan  / default
_CP_SEL      = 3   # selected row              black / cyan
_CP_ACCENT   = 4   # accent (fluent blue)      cyan  / default  bold
_CP_TASKBAR  = 5   # bottom status bar         black / white
_CP_ERR      = 6   # error / warning           red   / default
_CP_OK       = 7   # success                   green / default
_CP_DIM      = 8   # secondary / placeholder   white / default
_CP_INPUT    = 9   # inactive input field      white / default
_CP_FOCUS    = 10  # focused input field       white / blue
_CP_BADGE    = 11  # info badge                black / cyan

def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(_CP_TITLEBAR, curses.COLOR_WHITE,  curses.COLOR_BLUE)
    curses.init_pair(_CP_BORDER,   curses.COLOR_CYAN,   -1)
    curses.init_pair(_CP_SEL,      curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(_CP_ACCENT,   curses.COLOR_CYAN,   -1)
    curses.init_pair(_CP_TASKBAR,  curses.COLOR_BLACK,  curses.COLOR_WHITE)
    curses.init_pair(_CP_ERR,      curses.COLOR_RED,    -1)
    curses.init_pair(_CP_OK,       curses.COLOR_GREEN,  -1)
    curses.init_pair(_CP_DIM,      curses.COLOR_WHITE,  -1)
    curses.init_pair(_CP_INPUT,    curses.COLOR_WHITE,  curses.COLOR_BLACK)
    curses.init_pair(_CP_FOCUS,    curses.COLOR_WHITE,  curses.COLOR_BLUE)
    curses.init_pair(_CP_BADGE,    curses.COLOR_BLACK,  curses.COLOR_CYAN)

# ══════════════════════════════════════════════════════════════════════════════
# Drawing primitives
# ══════════════════════════════════════════════════════════════════════════════

def _put(win: curses.window, y: int, x: int, s: str, attr: int = 0) -> None:
    """Safe addstr – silently absorbs boundary errors."""
    try:
        h, w = win.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1:
            win.addstr(y, x, s[: w - x - 1], attr)
    except curses.error:
        pass

def _draw_box(
    win: curses.window,
    y: int, x: int, h: int, w: int,
    title: str = "",
    attr: int = 0,
    fill: bool = False,
) -> None:
    """Rounded box (╭╮╯╰) – Windows 11 Fluent rounded corners."""
    if not attr:
        attr = curses.color_pair(_CP_BORDER)
    try:
        if fill:
            for r in range(y + 1, y + h - 1):
                _put(win, r, x + 1, " " * (w - 2))
        win.addch(y,     x,     "╭", attr)
        win.addch(y,     x+w-1, "╮", attr)
        win.addch(y+h-1, x,     "╰", attr)
        win.addch(y+h-1, x+w-1, "╯", attr)
        for i in range(1, w - 1):
            win.addch(y,     x+i, "─", attr)
            win.addch(y+h-1, x+i, "─", attr)
        for i in range(1, h - 1):
            win.addch(y+i, x,     "│", attr)
            win.addch(y+i, x+w-1, "│", attr)
        if title:
            t  = f" {title} "
            tx = x + max(1, (w - len(t)) // 2)
            _put(win, y, tx, t, attr | curses.A_BOLD)
    except curses.error:
        pass

def _titlebar(stdscr: curses.window, subtitle: str = "") -> None:
    """Persistent title bar with breadcrumb and live clock."""
    _, w = stdscr.getmaxyx()
    now  = datetime.datetime.now().strftime("%H:%M:%S")
    user = os.environ.get("USER", "")
    left = f"  cronmgr{('  ›  ' + subtitle) if subtitle else ''}"
    right = f" {user}  {now} "
    bar  = left.ljust(w - len(right)) + right
    try:
        stdscr.addstr(0, 0, bar[: w - 1], curses.color_pair(_CP_TITLEBAR) | curses.A_BOLD)
        stdscr.addch(0, w - 1, " ", curses.color_pair(_CP_TITLEBAR))
    except curses.error:
        pass

def _taskbar(stdscr: curses.window, keys: list[tuple[str, str]]) -> None:
    """Windows 11 taskbar-style key-hint strip at the bottom."""
    h, w = stdscr.getmaxyx()
    x = 0
    try:
        stdscr.addstr(h - 1, 0, " " * (w - 1), curses.color_pair(_CP_TASKBAR))
        for key, desc in keys:
            chunk = f" {key} "
            desc_chunk = f" {desc}  "
            if x + len(chunk) + len(desc_chunk) >= w:
                break
            stdscr.addstr(h - 1, x, chunk,
                          curses.color_pair(_CP_ACCENT) | curses.A_BOLD | curses.A_REVERSE)
            x += len(chunk)
            stdscr.addstr(h - 1, x, desc_chunk, curses.color_pair(_CP_TASKBAR))
            x += len(desc_chunk)
    except curses.error:
        pass

def _toast(stdscr: curses.window, msg: str, ok: bool = True) -> None:
    """Windows 11-style toast notification (centre-bottom, auto-dismiss)."""
    h, w = stdscr.getmaxyx()
    inner = f"  {msg}  "
    tw    = len(inner) + 2
    tx    = max(0, (w - tw) // 2)
    ty    = max(2, h - 4)
    attr  = curses.color_pair(_CP_OK) if ok else curses.color_pair(_CP_ERR)
    _draw_box(stdscr, ty, tx, 3, tw,
              attr=attr | curses.A_BOLD, fill=True)
    _put(stdscr, ty + 1, tx + 1, inner, attr | curses.A_BOLD)
    stdscr.refresh()
    curses.napms(1600)

def _modal(
    stdscr: curses.window,
    title: str,
    lines: list[str],
    confirm: bool = True,
) -> bool:
    """Centred Windows 11-style dialog. Returns True if Confirm/OK pressed."""
    h, w   = stdscr.getmaxyx()
    pad    = 6
    dw     = min(w - 4, max(48, max((len(l) for l in lines), default=0) + pad))
    dh     = len(lines) + (6 if confirm else 5)
    dy     = max(1, (h - dh) // 2)
    dx     = max(0, (w - dw) // 2)
    sel    = 1   # default: right button (OK/Confirm)

    while True:
        _draw_box(stdscr, dy, dx, dh, dw, title=title,
                  attr=curses.color_pair(_CP_ACCENT) | curses.A_BOLD, fill=True)
        for i, line in enumerate(lines):
            _put(stdscr, dy + 2 + i, dx + 3, line[: dw - 6])

        if confirm:
            by = dy + dh - 2
            b_no   = "  Cancel  "
            b_yes  = "  Confirm  "
            bx_yes = dx + dw - len(b_yes) - 3
            bx_no  = bx_yes - len(b_no) - 2
            _put(stdscr, by, bx_no,
                 b_no,
                 curses.color_pair(_CP_SEL) if sel == 0 else curses.color_pair(_CP_DIM))
            _put(stdscr, by, bx_yes,
                 b_yes,
                 (curses.color_pair(_CP_ACCENT) | curses.A_BOLD) if sel == 1
                 else curses.color_pair(_CP_DIM))
            _taskbar(stdscr, [("←→", "Switch"), ("↵", "Select"), ("Esc", "Cancel")])
        else:
            by  = dy + dh - 2
            bx  = dx + dw - 8
            _put(stdscr, by, bx, "  OK  ",
                 curses.color_pair(_CP_ACCENT) | curses.A_BOLD)
            _taskbar(stdscr, [("↵", "Close")])

        stdscr.refresh()
        key = stdscr.getch()

        if not confirm:
            return True

        if key in (curses.KEY_LEFT, curses.KEY_RIGHT, ord("\t")):
            sel = 1 - sel
        elif key in (curses.KEY_ENTER, 10, 13):
            return sel == 1
        elif key in (ord("y"), ord("Y")):
            return True
        elif key in (ord("n"), ord("N"), 27):
            return False

# ══════════════════════════════════════════════════════════════════════════════
# In-TUI single-line text input
# ══════════════════════════════════════════════════════════════════════════════

def _readline(
    stdscr: curses.window,
    y: int, x: int, width: int,
    initial: str = "",
    placeholder: str = "",
) -> tuple[str, str]:
    """
    Inline text editor.  Returns (text, reason).
    reason: 'enter' | 'escape' | 'tab' | 'backtab'
    """
    buf  = list(initial)
    pos  = len(buf)
    scrl = 0                 # horizontal scroll offset
    view = max(1, width)     # visible character count – guard against ≤0

    while True:
        # Adjust horizontal scroll
        if pos - scrl >= view:
            scrl = pos - view + 1
        if pos < scrl:
            scrl = pos

        visible_text = "".join(buf)[scrl: scrl + view]

        if not buf and placeholder:
            _put(stdscr, y, x, placeholder[:view].ljust(view), curses.color_pair(_CP_DIM))
        else:
            _put(stdscr, y, x, visible_text.ljust(view), curses.color_pair(_CP_FOCUS))

        try:
            stdscr.move(y, x + min(pos - scrl, view - 1))
        except curses.error:
            pass
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            return "".join(buf), "enter"
        elif key == 27:
            return "".join(buf), "escape"
        elif key == ord("\t"):
            return "".join(buf), "tab"
        elif key == curses.KEY_BTAB:
            return "".join(buf), "backtab"
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0:
                buf.pop(pos - 1)
                pos -= 1
        elif key == curses.KEY_DC:
            if pos < len(buf):
                buf.pop(pos)
        elif key == curses.KEY_LEFT:
            pos = max(0, pos - 1)
        elif key == curses.KEY_RIGHT:
            pos = min(len(buf), pos + 1)
        elif key == curses.KEY_HOME:
            pos, scrl = 0, 0
        elif key == curses.KEY_END:
            pos = len(buf)
        elif 32 <= key <= 126:
            buf.insert(pos, chr(key))
            pos += 1

# ══════════════════════════════════════════════════════════════════════════════
# TUI screens
# ══════════════════════════════════════════════════════════════════════════════

# ── Main menu ─────────────────────────────────────────────────────────────────

_MENU: list[tuple[str, str]] = [
    ("  List jobs",      "View all scheduled cron jobs"),
    ("  Add job",        "Create a new cron job entry"),
    ("  Delete job(s)",  "Remove one or more cron jobs"),
    ("  Edit in $EDITOR","Open crontab in your default editor"),
    ("  Clear all jobs", "Remove every cron job for this user"),
    ("  Quit",           "Exit cronmgr"),
]

def _screen_main(stdscr: curses.window, user: str | None) -> int:
    """
    Windows 11 Settings-style main menu.
    Returns selected index (0–5) or -1 on q / Esc.
    """
    sel = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        _titlebar(stdscr)

        # Reload job count for badge
        try:
            entries  = load_entries(user)
            job_cnt  = sum(1 for e in entries if e.is_job)
            badge    = f" {job_cnt} job{'s' if job_cnt != 1 else ''} "
        except RuntimeError:
            badge = " ? jobs "

        # Outer card
        card_w = min(w - 4, 62)
        card_h = len(_MENU) * 3 + 4
        card_y = max(1, (h - card_h) // 2)
        card_x = max(0, (w - card_w) // 2)

        _draw_box(stdscr, card_y, card_x, card_h, card_w,
                  title=" ⚙  cronmgr ",
                  attr=curses.color_pair(_CP_ACCENT) | curses.A_BOLD,
                  fill=True)

        # Badge (top-right inside card)
        _put(stdscr, card_y, card_x + card_w - len(badge) - 2,
             badge, curses.color_pair(_CP_BADGE) | curses.A_BOLD)

        # Menu rows (each takes 2 lines: title + description)
        for i, (label, desc) in enumerate(_MENU):
            ry = card_y + 2 + i * 2
            is_sel = i == sel
            lbl_a = (curses.color_pair(_CP_SEL) | curses.A_BOLD) if is_sel else curses.A_BOLD
            dsc_a = curses.color_pair(_CP_SEL) if is_sel else curses.color_pair(_CP_DIM)
            arrow = "▶" if is_sel else " "
            _put(stdscr, ry,     card_x + 2, f" {arrow} {label:<30}", lbl_a)
            _put(stdscr, ry + 1, card_x + 2, f"     {desc:<35}", dsc_a)

        _taskbar(stdscr, [("↑↓", "Navigate"), ("↵", "Select"), ("Q", "Quit")])
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            sel = (sel - 1) % len(_MENU)
        elif key in (curses.KEY_DOWN, ord("j")):
            sel = (sel + 1) % len(_MENU)
        elif key in (curses.KEY_ENTER, 10, 13):
            return sel
        elif key in (ord("q"), ord("Q"), 27):
            return -1

# ── List view ─────────────────────────────────────────────────────────────────

def _screen_list(stdscr: curses.window, user: str | None) -> None:
    """Scrollable job table with live search (press / to filter)."""
    entries  = load_entries(user)
    all_jobs = [e for e in entries if e.is_job]
    query    = ""
    cur      = 0
    off      = 0

    while True:
        jobs    = (
            [j for j in all_jobs
             if query.lower() in j.schedule.lower()
             or query.lower() in j.command.lower()
             or query.lower() in j.comment.lower()]
            if query else all_jobs
        )
        cur     = min(cur, max(0, len(jobs) - 1))

        stdscr.erase()
        h, w    = stdscr.getmaxyx()
        _titlebar(stdscr, "List Jobs")

        bw      = w - 4
        bh      = h - 4
        by      = 2
        bx      = 2
        visible = bh - 4          # rows available for jobs
        title   = f" {len(all_jobs)} job{'s' if len(all_jobs) != 1 else ''} "
        if query:
            title = f" /{query}  {len(jobs)} match{'es' if len(jobs)!=1 else ''} "

        _draw_box(stdscr, by, bx, bh, bw,
                  title=title,
                  attr=curses.color_pair(_CP_ACCENT) | curses.A_BOLD,
                  fill=True)

        # Column headers
        col_w = bw - 6
        _put(stdscr, by + 1, bx + 2,
             f"{'#':>3}  {'SCHEDULE':<22}  {'COMMAND':<{col_w - 28}}",
             curses.color_pair(_CP_DIM) | curses.A_BOLD)
        _put(stdscr, by + 2, bx + 2, "─" * (bw - 4), curses.color_pair(_CP_BORDER))

        # Scroll adjustment
        if cur < off:
            off = cur
        if cur >= off + visible:
            off = cur - visible + 1

        if not jobs:
            _put(stdscr, by + 4, bx + 4,
                 "No matching jobs." if query else "No cron jobs found.",
                 curses.color_pair(_CP_DIM))
        else:
            for row, job in enumerate(jobs[off: off + visible]):
                y   = by + 3 + row
                gi  = row + off
                sel = gi == cur
                base  = curses.color_pair(_CP_SEL)   if sel else curses.A_NORMAL
                sched = curses.color_pair(_CP_SEL)   if sel else (curses.color_pair(_CP_ACCENT) | curses.A_BOLD)
                cmd_w = max(1, bw - 36)
                try:
                    stdscr.addstr(y, bx + 2, f"{job.index:>3}  ", base)
                    stdscr.addstr(y, bx + 7, f"{job.schedule:<22}  ", sched)
                    stdscr.addstr(y, bx + 31, job.command[:cmd_w], base)
                    if job.comment:
                        stdscr.addstr(y, bx + 31 + min(len(job.command), cmd_w),
                                      f"  # {job.comment}"[: bw - 31 - len(job.command) - 2],
                                      curses.color_pair(_CP_DIM))
                except curses.error:
                    pass

            # Scroll position indicator
            if len(jobs) > visible:
                pct = int(100 * cur / max(1, len(jobs) - 1))
                _put(stdscr, by + bh - 2, bx + bw - 7,
                     f" {pct:3d}% ", curses.color_pair(_CP_BADGE))

        # Search bar at bottom of box
        if query:
            _put(stdscr, by + bh - 1, bx + 2,
                 f" / {query} ", curses.color_pair(_CP_FOCUS) | curses.A_BOLD)

        _taskbar(stdscr, [
            ("↑↓", "Navigate"), ("PgUp/Dn", "Page"),
            ("/", "Search"), ("r", "Reload"), ("Esc", "Back"),
        ])
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            cur = max(0, cur - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cur = min(max(0, len(jobs) - 1), cur + 1)
        elif key == curses.KEY_PPAGE:
            cur = max(0, cur - visible)
        elif key == curses.KEY_NPAGE:
            cur = min(max(0, len(jobs) - 1), cur + visible)
        elif key == ord("/"):
            # Inline search input
            stdscr.erase()
            _titlebar(stdscr, "List Jobs · Search")
            _draw_box(stdscr, by, bx, bh, bw,
                      title=" Search ",
                      attr=curses.color_pair(_CP_ACCENT) | curses.A_BOLD,
                      fill=True)
            _put(stdscr, by + 2, bx + 3, "Filter by schedule, command, or comment:")
            _put(stdscr, by + 3, bx + 3, " / ")
            _draw_box(stdscr, by + 4, bx + 3, 3, max(4, bw - 6),
                      attr=curses.color_pair(_CP_FOCUS) | curses.A_BOLD, fill=True)
            _taskbar(stdscr, [("↵", "Apply"), ("Esc", "Cancel")])
            curses.curs_set(1)
            text, reason = _readline(stdscr, by + 5, bx + 4, max(1, bw - 8), initial=query)
            curses.curs_set(0)
            if reason in ("enter", "tab"):
                query = text.strip()
                cur   = 0
                off   = 0
        elif key in (ord("r"), ord("R")):
            entries  = load_entries(user)
            all_jobs = [e for e in entries if e.is_job]
            cur = min(cur, max(0, len(all_jobs) - 1))
            off = 0
        elif key == 27:
            if query:
                query = ""
                cur   = 0
                off   = 0
            else:
                return
        elif key in (ord("q"), ord("Q")):
            return

# ── Add form ──────────────────────────────────────────────────────────────────

# Field layout: (label_row_offset, input_box_row_offset, input_content_row_offset)
_FORM_FIELDS: list[tuple[str, str, int, int, int]] = [
    # label           placeholder                        lbl_off  box_off  inp_off
    ("Schedule",  "*/5 * * * *    @daily    @reboot",       2,       3,      4),
    ("Command",   "/path/to/command.sh",                    7,       8,      9),
    ("Comment",   "optional description",                  12,      13,     14),
]

def _screen_add(stdscr: curses.window, user: str | None) -> None:
    """Windows 11-style in-TUI form – no terminal suspension needed."""
    h, w   = stdscr.getmaxyx()
    fw     = min(w - 4, 68)
    fh     = 19
    fy     = max(1, (h - fh) // 2)
    fx     = max(0, (w - fw) // 2)
    iw     = max(1, fw - 10)   # inner input width – guard against narrow terminals

    fields = ["", "", ""]
    errors = ["", "", ""]
    cur_f  = 0

    while True:
        stdscr.erase()
        _titlebar(stdscr, "Add Job")
        _draw_box(stdscr, fy, fx, fh, fw,
                  title=" ➕  New Cron Job ",
                  attr=curses.color_pair(_CP_ACCENT) | curses.A_BOLD,
                  fill=True)

        for i, (label, placeholder, loff, boff, ioff) in enumerate(_FORM_FIELDS):
            is_cur   = i == cur_f
            lbl_attr = (curses.color_pair(_CP_ACCENT) | curses.A_BOLD) if is_cur \
                       else curses.color_pair(_CP_DIM)
            box_attr = (curses.color_pair(_CP_FOCUS) | curses.A_BOLD) if is_cur \
                       else curses.color_pair(_CP_BORDER)

            _put(stdscr, fy + loff, fx + 4, label, lbl_attr)
            if errors[i]:
                _put(stdscr, fy + loff, fx + 4 + len(label) + 2,
                     f"⚠  {errors[i]}", curses.color_pair(_CP_ERR))
            _draw_box(stdscr, fy + boff, fx + 4, 3, fw - 8,
                      attr=box_attr, fill=True)

            if i != cur_f:
                if fields[i]:
                    _put(stdscr, fy + ioff, fx + 5, fields[i][:iw])
                else:
                    _put(stdscr, fy + ioff, fx + 5, placeholder[:iw],
                         curses.color_pair(_CP_DIM))

        # Buttons
        btn_y      = fy + fh - 2
        b_cancel   = "  ✕  Cancel  "
        b_add      = "  ✓  Add Job  "
        bx_add     = fx + fw - len(b_add) - 3
        bx_cancel  = bx_add - len(b_cancel) - 2
        _put(stdscr, btn_y, bx_cancel, b_cancel, curses.color_pair(_CP_DIM))
        _put(stdscr, btn_y, bx_add,    b_add,
             curses.color_pair(_CP_ACCENT) | curses.A_BOLD)

        _taskbar(stdscr, [
            ("Tab", "Next field"),
            ("Shift+Tab", "Prev"),
            ("↵", "Confirm"),
            ("Esc", "Cancel"),
        ])

        _, _, _, _, ioff = _FORM_FIELDS[cur_f]
        curses.curs_set(1)
        text, reason = _readline(
            stdscr,
            y=fy + ioff, x=fx + 5, width=iw,
            initial=fields[cur_f],
            placeholder=_FORM_FIELDS[cur_f][1],
        )
        curses.curs_set(0)

        fields[cur_f] = text
        errors[cur_f] = ""

        if reason == "escape":
            return
        elif reason == "tab":
            cur_f = (cur_f + 1) % 3
        elif reason == "backtab":
            cur_f = (cur_f - 1) % 3
        elif reason == "enter":
            # Validate
            sched   = fields[0].strip()
            cmd     = fields[1].strip()
            valid   = True

            if not sched:
                errors[0] = "Required"
                valid = False
            elif not (sched.split()[0].startswith("@") or len(sched.split()) == 5):
                errors[0] = "5 fields or @keyword"
                valid = False
            if not cmd:
                errors[1] = "Required"
                valid = False

            if not valid:
                cur_f = 0 if errors[0] else 1
                continue

            comment  = fields[2].strip()
            inline   = f"  # {comment}" if comment else ""
            new_line = f"{sched}  {cmd}{inline}"

            # Confirm via modal dialog (stays in curses!)
            if _modal(stdscr, " Confirm ", [
                "The following job will be added:",
                "",
                f"  {new_line[:58]}",
            ]):
                try:
                    entries = load_entries(user)
                    entries.append(CronEntry(
                        index=len(entries) + 1,
                        raw=new_line, is_job=True,
                        schedule=sched, command=cmd, comment=comment,
                    ))
                    save_entries(entries, user)
                    _toast(stdscr, "Job added successfully")
                except RuntimeError as exc:
                    _toast(stdscr, f"Error: {exc}", ok=False)
            return

# ── Delete screen ─────────────────────────────────────────────────────────────

def _screen_delete(stdscr: curses.window, user: str | None) -> None:
    """Multi-select with Space, modal confirmation – fully in curses."""
    entries = load_entries(user)
    jobs    = [e for e in entries if e.is_job]

    if not jobs:
        _modal(stdscr, " Delete ", ["No cron jobs found."], confirm=False)
        return

    selected: set[int] = set()
    cur  = 0
    off  = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        _titlebar(stdscr, "Delete Jobs")

        bw      = w - 4
        bh      = h - 4
        by      = 2
        bx      = 2
        visible = bh - 2
        badge   = f" {len(selected)} selected " if selected else " Space to select "

        _draw_box(stdscr, by, bx, bh, bw,
                  title=f" Delete Jobs  ·{badge}",
                  attr=curses.color_pair(_CP_ERR if selected else _CP_ACCENT) | curses.A_BOLD,
                  fill=True)

        if cur < off:
            off = cur
        if cur >= off + visible:
            off = cur - visible + 1

        for row, job in enumerate(jobs[off: off + visible]):
            y   = by + 1 + row
            gi  = row + off
            sel = gi == cur
            chk = gi in selected
            chk_attr  = (curses.color_pair(_CP_OK) | curses.A_BOLD) if chk \
                        else curses.color_pair(_CP_DIM)
            row_attr  = curses.color_pair(_CP_SEL) if sel else curses.A_NORMAL
            sched_attr = curses.color_pair(_CP_SEL) if sel else (curses.color_pair(_CP_ACCENT) | curses.A_BOLD)
            cmd_w     = max(1, bw - 36)

            _put(stdscr, y, bx + 2, "●" if chk else "○", chk_attr)
            try:
                stdscr.addstr(y, bx + 4, f"{job.schedule:<22}  ", sched_attr)
                stdscr.addstr(y, bx + 28, job.command[:cmd_w], row_attr)
            except curses.error:
                pass

        if len(jobs) > visible:
            pct = int(100 * cur / max(1, len(jobs) - 1))
            _put(stdscr, by + bh - 2, bx + bw - 7,
                 f" {pct:3d}% ", curses.color_pair(_CP_BADGE))

        _taskbar(stdscr, [
            ("↑↓", "Navigate"),
            ("Space", "Toggle"),
            ("↵", f"Delete {len(selected)}" if selected else "Confirm"),
            ("q", "Back"),
        ])
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            cur = max(0, cur - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cur = min(len(jobs) - 1, cur + 1)
        elif key == ord(" "):
            selected.symmetric_difference_update({cur})
        elif key in (curses.KEY_ENTER, 10, 13):
            if not selected:
                continue
            targets = sorted(selected)
            lines   = [f"  {jobs[i].schedule:<22}  {jobs[i].command[:36]}"
                       for i in targets]
            if _modal(stdscr, f" Delete {len(targets)} job(s)? ", lines):
                remove_idx = {jobs[i].index for i in targets}
                kept = [e for e in entries if e.index not in remove_idx]
                try:
                    save_entries(kept, user)
                    _toast(stdscr, f"{len(targets)} job(s) removed")
                except RuntimeError as exc:
                    _toast(stdscr, f"Error: {exc}", ok=False)
                return
        elif key in (ord("q"), ord("Q"), 27):
            return

# ── Clear screen ──────────────────────────────────────────────────────────────

def _screen_clear(stdscr: curses.window, user: str | None) -> None:
    """Full-screen warning + modal confirmation before crontab -r."""
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    _titlebar(stdscr, "Clear All")

    dw = min(w - 4, 56)
    dh = 10
    dy = max(1, (h - dh) // 2)
    dx = max(0, (w - dw) // 2)

    _draw_box(stdscr, dy, dx, dh, dw,
              title=" ⚠  Clear All Jobs ",
              attr=curses.color_pair(_CP_ERR) | curses.A_BOLD,
              fill=True)

    warn_lines = [
        "This will permanently delete ALL",
        "scheduled cron jobs for this user.",
        "",
        "This action cannot be undone.",
    ]
    for i, line in enumerate(warn_lines):
        attr = curses.color_pair(_CP_ERR) | curses.A_BOLD if i < 2 else curses.color_pair(_CP_DIM)
        _put(stdscr, dy + 2 + i, dx + 4, line, attr)

    stdscr.refresh()

    if _modal(stdscr, " Are you sure? ", ["Delete ALL cron jobs?"]):
        try:
            _run([*_cmd(user), "-r"])
            _toast(stdscr, "All cron jobs cleared")
        except RuntimeError as exc:
            _toast(stdscr, f"Error: {exc}", ok=False)

# ══════════════════════════════════════════════════════════════════════════════
# TUI root
# ══════════════════════════════════════════════════════════════════════════════

_MIN_W, _MIN_H = 60, 20   # minimum usable terminal dimensions

def _tui_root(stdscr: curses.window, user: str | None) -> None:
    h, w = stdscr.getmaxyx()
    if w < _MIN_W or h < _MIN_H:
        curses.endwin()
        print(
            f"ERROR: terminal too small ({w}×{h}). "
            f"cronmgr requires at least {_MIN_W}×{_MIN_H}.",
            file=sys.stderr,
        )
        return
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    _init_colors()

    while True:
        idx = _screen_main(stdscr, user)
        if idx < 0 or idx == 5:
            break
        match idx:
            case 0:
                _screen_list(stdscr, user)
            case 1:
                _screen_add(stdscr, user)
            case 2:
                _screen_delete(stdscr, user)
            case 3:
                curses.endwin()
                cmd_edit(user)
                input("  [press Enter to return]")
            case 4:
                _screen_clear(stdscr, user)
        stdscr.clear()

def launch_tui(user: str | None) -> None:
    curses.wrapper(_tui_root, user)

# ══════════════════════════════════════════════════════════════════════════════
# CLI commands  (unchanged, fully backward-compatible)
# ══════════════════════════════════════════════════════════════════════════════

def cmd_list(user: str | None, all_lines: bool) -> None:
    entries = load_entries(user)
    jobs    = [e for e in entries if e.is_job]
    if not jobs:
        print("No cron jobs found.")
        return
    w_sched = max(len(e.schedule) for e in jobs)
    print(f"{'#':>3}  {'SCHEDULE':<{w_sched}}  COMMAND")
    print("─" * (5 + w_sched + 40))
    for e in jobs:
        tag = f"  \033[90m# {e.comment}\033[0m" if e.comment else ""
        print(f"{e.index:>3}  {e.schedule:<{w_sched}}  {e.command}{tag}")
    if all_lines:
        print("\n── raw crontab ──")
        for e in entries:
            print(e.raw)

def cmd_add(
    user: str | None,
    schedule: str,
    command: str,
    comment: str,
    dry_run: bool,
) -> None:
    parts = schedule.split()
    if not (parts[0].startswith("@") or len(parts) == 5):
        print("ERROR: schedule must be 5 fields or @keyword", file=sys.stderr)
        sys.exit(1)
    inline   = f"  # {comment}" if comment else ""
    new_line = f"{schedule}  {command}{inline}"
    if dry_run:
        print(f"[dry-run] would add:\n  {new_line}")
        return
    entries = load_entries(user)
    entries.append(CronEntry(
        index=len(entries) + 1, raw=new_line, is_job=True,
        schedule=schedule, command=command, comment=comment,
    ))
    save_entries(entries, user)
    print(f"Added: {new_line}")

def cmd_delete(user: str | None, indices: list[int], dry_run: bool) -> None:
    entries = load_entries(user)
    job_map = {e.index: e for e in entries if e.is_job}
    idx_set = set(indices)
    for i in idx_set:
        if i not in job_map:
            print(f"ERROR: no job at line index {i}", file=sys.stderr)
            sys.exit(1)
    for i in sorted(idx_set):
        prefix = "[dry-run] would remove" if dry_run else "Removing"
        print(f"{prefix}:  {job_map[i]}")
    if dry_run:
        return
    kept = [e for e in entries if e.index not in idx_set]
    save_entries(kept, user)

def cmd_edit(user: str | None) -> None:
    import shutil
    editor = (os.environ.get("EDITOR")
              or os.environ.get("VISUAL")
              or shutil.which("vi")
              or "vi")
    raw = _run([*_cmd(user), "-l"])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    try:
        subprocess.run([editor, str(tmp)], check=False)
        new_content = tmp.read_text()
    finally:
        tmp.unlink(missing_ok=True)
    _run([*_cmd(user), "-"], input_data=new_content)
    print("Crontab updated.")

def cmd_clear(user: str | None, force: bool) -> None:
    if not force:
        if input("Remove ALL cron jobs? [y/N]: ").strip().lower() != "y":
            print("Aborted.")
            return
    _run([*_cmd(user), "-r"])
    print("Crontab cleared.")

# ══════════════════════════════════════════════════════════════════════════════
# CLI parser
# ══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cronmgr",
        description="Manage crontab entries. No subcommand → interactive TUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  cronmgr                                        # interactive TUI
  cronmgr list
  cronmgr list --all
  cronmgr add "*/5 * * * *" "/usr/bin/script.sh" --comment "every 5 min"
  cronmgr add "@reboot" "/opt/start.sh" -n       # dry-run
  cronmgr delete 3
  cronmgr delete 1 4 7
  cronmgr edit
  cronmgr clear --force
  cronmgr -u www-data list
""",
    )
    p.add_argument("-u", "--user", metavar="USER",
                   help="target user (default: current user, root needed for others)")
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", aliases=["ls"], help="show cron jobs")
    ls.add_argument("-a", "--all", dest="all_lines", action="store_true",
                    help="include comment / blank lines in output")

    add = sub.add_parser("add", help="add a new cron job")
    add.add_argument("schedule", help='"*/5 * * * *"  or  "@daily"')
    add.add_argument("command",  help="command to execute")
    add.add_argument("-c", "--comment", default="", help="inline comment")
    add.add_argument("-n", "--dry-run", action="store_true")

    rm = sub.add_parser("delete", aliases=["rm", "del"],
                        help="remove job(s) by line index")
    rm.add_argument("index", nargs="+", type=int,
                    help="line index from 'list' output")
    rm.add_argument("-n", "--dry-run", action="store_true")

    sub.add_parser("edit", help="open crontab in $EDITOR")

    clr = sub.add_parser("clear", help="remove all cron jobs")
    clr.add_argument("-f", "--force", action="store_true",
                     help="skip confirmation prompt")

    return p

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    try:
        if args.cmd is None:
            launch_tui(args.user)
            return

        match args.cmd:
            case "list" | "ls":
                cmd_list(args.user, args.all_lines)
            case "add":
                cmd_add(args.user, args.schedule, args.command,
                        args.comment, args.dry_run)
            case "delete" | "rm" | "del":
                cmd_delete(args.user, args.index, args.dry_run)
            case "edit":
                cmd_edit(args.user)
            case "clear":
                cmd_clear(args.user, args.force)

    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)

if __name__ == "__main__":
    main()
