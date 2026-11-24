"""窗口探测：列进程窗口/子窗口、移动、最大化、前置。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

u = ctypes.windll.user32


def _text(hwnd):
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect(hwnd):
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def _pid(hwnd):
    p = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def list_windows(pid: int | None, want_child: bool = False):
    rows = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        rows.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    out = []
    for h in rows:
        if pid and _pid(h) != pid:
            continue
        out.append((h, _text(h), _class(h), _rect(h), bool(u.IsWindowVisible(h)),
                    bool(u.IsIconic(h)), _find_child_text(h) if want_child else ""))
    return out


def _find_child_text(hwnd, depth: int = 2) -> str:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(ch, _):
        t = _text(ch)
        c = _class(ch)
        if t or c.lower().startswith("chrome"):
            found.append(f"{c}:{t[:30]}")
        return True

    u.EnumChildWindows(hwnd, cb, 0)
    return " | ".join(found[:6])


def move(hwnd, x, y, w, h):
    SWP = 0x0040 | 0x0004  # SWP_SHOWWINDOW | SWP_NOZORDER
    u.SetWindowPos(hwnd, 0, x, y, w, h, SWP)


def show(hwnd, mode=9):
    u.ShowWindow(hwnd, mode)


def fg(hwnd):
    u.ShowWindow(hwnd, 9)
    u.SetForegroundWindow(hwnd)
    u.BringWindowToTop(hwnd)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "list":
        pid = int(argv[1]) if len(argv) > 1 else None
        for h, t, c, r, vis, ico, kids in list_windows(pid, want_child=True):
            print(f"hwnd={h:<10} pid={_pid(h):<7} vis={int(vis)} min={int(ico)} rect={r} class={c!r} title={t!r}")
            if kids:
                print(f"           kids: {kids}")
    elif cmd == "move":
        move(int(argv[1]), int(argv[2]), int(argv[3]), int(argv[4]), int(argv[5]))
        print("moved")
    elif cmd == "show":
        show(int(argv[1]), int(argv[2]) if len(argv) > 2 else 9)
        print("shown")
    elif cmd == "fg":
        fg(int(argv[1]))
        print("foreground")
    else:
        print("未知命令")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
