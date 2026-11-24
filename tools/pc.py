"""极简桌面操作：截图 / 点击 / 按键 / 列窗口（纯 ctypes + Pillow，不依赖 MCP）。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.windll.user32


def screenshot(path: str = "shot.png") -> str:
    from PIL import ImageGrab

    img = ImageGrab.grab(all_screens=True)
    img.save(path)
    return f"{path} {img.size}"


def move(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def click(x: int, y: int, button: str = "left", times: int = 1) -> None:
    down = 0x0002 if button == "left" else 0x0008
    up = 0x0004 if button == "left" else 0x0010
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    for _ in range(times):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.12)


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    user32.SetCursorPos(int(x1), int(y1))
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    steps = 18
    for i in range(1, steps + 1):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.02)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


KEYS = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20, "backspace": 0x08,
        "f5": 0x74, "pagedown": 0x22, "pageup": 0x21, "down": 0x28, "up": 0x26,
        "left": 0x25, "right": 0x27}


def key(name: str) -> str:
    vk = KEYS.get(name.lower())
    if vk is None:
        return f"未知按键 {name}"
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 2, 0)
    return f"key {name}"


def windows() -> str:
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((buf.value, (r.left, r.top, r.right, r.bottom), pid.value, hwnd))
        return True

    user32.EnumWindows(cb, 0)
    lines = [f"{t!r:<48} rect={rect} pid={pid} hwnd={hwnd}" for t, rect, pid, hwnd in out]
    return "\n".join(lines)


def foreground(hwnd: int) -> str:
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return f"foreground {hwnd}"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "shot":
        print(screenshot(rest[0] if rest else "shot.png"))
    elif cmd == "windows":
        print(windows())
    elif cmd == "click":
        click(int(rest[0]), int(rest[1]), rest[2] if len(rest) > 2 else "left",
              int(rest[3]) if len(rest) > 3 else 1)
        print("clicked")
    elif cmd == "move":
        move(int(rest[0]), int(rest[1]))
        print("moved")
    elif cmd == "drag":
        drag(*[int(v) for v in rest[:4]])
        print("dragged")
    elif cmd == "key":
        print(key(rest[0]))
    elif cmd == "fg":
        print(foreground(int(rest[0])))
    else:
        print(f"未知命令 {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
