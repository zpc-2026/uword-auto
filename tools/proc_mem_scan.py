"""只读扫描进程内存里的字符串（找 token / 接口域名用）。

    python tools/proc_mem_scan.py --pid 146552 --pattern eyJ
    python tools/proc_mem_scan.py --pid 146552 --pattern word.fltrp.com

只做 ReadProcessMemory，不写、不注入。
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wt.BOOL
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p) if False else ctypes.c_void_p, ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
PAGE_READABLE = {0x02, 0x04, 0x20, 0x40}  # READONLY, READWRITE, EXECUTE_READ, EXECUTE_READWRITE


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


def printable_context(buf: bytes, idx: int, before: int = 60, after: int = 160) -> str:
    s = max(0, idx - before)
    e = min(len(buf), idx + after)
    raw = buf[s:e]
    out = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
    return out


def scan(pid: int, patterns: list[bytes], limit: int = 20) -> int:
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        err = ctypes.get_last_error()
        print(f"OpenProcess 失败 pid={pid} err={err}")
        return 1
    print(f"已打开进程 {pid}")
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    mbi_size = ctypes.sizeof(mbi)
    found = {p: 0 for p in patterns}
    scanned = 0
    try:
        while kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), mbi_size):
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize or 0
            if size == 0:
                break
            if mbi.State == MEM_COMMIT and mbi.Protect in PAGE_READABLE and size <= 64 * 1024 * 1024:
                buf = ctypes.create_string_buffer(size)
                read = ctypes.c_size_t(0)
                ok = kernel32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(read))
                if ok:
                    data = buf.raw[: read.value]
                    scanned += 1
                    for p in patterns:
                        start = 0
                        while True:
                            idx = data.find(p, start)
                            if idx < 0:
                                break
                            found[p] += 1
                            if found[p] <= limit:
                                print(f"\n[{p.decode('latin-1')}] @0x{base + idx:X}")
                                print("  " + printable_context(data, idx))
                            start = idx + 1
            addr = base + size
            if addr > 0x7FFFFFFFFFFF:
                break
    finally:
        kernel32.CloseHandle(h)
    print(f"\n扫描区块 {scanned} 个")
    for p, n in found.items():
        print(f"  {p.decode('latin-1')}: {n} 处")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--pattern", action="append", required=True)
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    return scan(args.pid, [p.encode() for p in args.pattern], args.limit)


if __name__ == "__main__":
    sys.exit(main())
