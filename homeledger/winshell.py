"""Windows taskbar identity for the app window.

HomeLedger is shown in an Edge/Chrome "app" window, which Windows treats as Edge: the taskbar shows the Edge logo and a
pinned button opens Edge's home page. This gives that window its own identity (name, icon and 'how to open me'), so
it groups with HomeLedger's shortcuts, shows the HomeLedger icon, and a pinned button starts HomeLedger.
Everything here is best-effort: any failure is ignored and the app works exactly as before."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

APP_ID = "HomeLedger.App"


def _set_props(hwnd: int, exe: str) -> bool:
    import ctypes
    from ctypes import POINTER, Structure, Union, byref, c_void_p, c_ulong, c_ushort, c_wchar_p, wintypes

    class GUID(Structure):
        _fields_ = [("a", c_ulong), ("b", c_ushort), ("c", c_ushort), ("d", ctypes.c_ubyte * 8)]

    class PROPERTYKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class _PV(Union):
        _fields_ = [("p", c_void_p), ("pad", ctypes.c_ulonglong * 2)]

    class PROPVARIANT(Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("u", _PV)]

    def guid(s: str) -> GUID:
        g = GUID()
        ctypes.oledll.ole32.CLSIDFromString(c_wchar_p(s), byref(g))
        return g

    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    iid = guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")        # IPropertyStore
    store = c_void_p()
    shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, POINTER(GUID), POINTER(c_void_p)]
    if shell32.SHGetPropertyStoreForWindow(hwnd, byref(iid), byref(store)) != 0 or not store:
        return False
    vtbl = ctypes.cast(ctypes.cast(store, POINTER(c_void_p))[0], POINTER(c_void_p))
    SetValue = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(vtbl[6])
    Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p)(vtbl[7])
    Release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])
    fmt = guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")        # System.AppUserModel.*
    ole32.CoTaskMemAlloc.restype = c_void_p
    ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]

    def put(pid: int, text: str) -> None:
        buf = ole32.CoTaskMemAlloc((len(text) + 1) * 2)
        ctypes.memmove(buf, ctypes.create_unicode_buffer(text), (len(text) + 1) * 2)
        pv = PROPVARIANT()
        pv.vt = 31                                              # VT_LPWSTR
        pv.u.p = buf
        SetValue(store, byref(PROPERTYKEY(fmt, pid)), byref(pv))   # the store takes its own copy
        ole32.CoTaskMemFree(c_void_p(buf))

    put(5, APP_ID)                                              # AppUserModelID
    put(2, f'"{exe}"')                                          # RelaunchCommand
    put(3, f"{exe},0")                                          # RelaunchIconResource
    put(4, "HomeLedger")                                        # RelaunchDisplayNameResource
    Commit(store)
    Release(store)
    return True


def _find_windows() -> list:
    """All visible browser windows showing HomeLedger (class check keeps a folder called 'HomeLedger' out)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if "HomeLedger" in buf.value:
                    cls = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls, 256)
                    if cls.value.startswith("Chrome_WidgetWin"):
                        found.append(hwnd)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return found


def _find_window() -> int:
    f = _find_windows()
    return f[0] if f else 0


def show_existing_window() -> bool:
    """If HomeLedger is already open, bring it to the front (restoring it if minimised) and say so."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        hwnd = _find_window()
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.keybd_event(0x12, 0, 0, 0)       # a tap of Alt lets Windows allow the focus change
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def brand_window_async(timeout: float = 25.0) -> None:
    """Wait for the HomeLedger window to appear, then give it HomeLedger's taskbar identity."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    exe = sys.executable

    def work():
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            end = time.time() + timeout
            done = set()
            while time.time() < end:
                wins = _find_windows()
                if wins:
                    for hwnd in wins:
                        if _set_props(hwnd, exe):
                            done.add(hwnd)
                    logging.getLogger("homeledger").info("taskbar identity set")
                    time.sleep(1.0)
                    for hwnd in _find_windows():
                        _set_props(hwnd, exe)                   # once more in case the browser reset it
                    return
                time.sleep(0.4)
        except Exception:
            logging.getLogger("homeledger").debug("taskbar identity failed", exc_info=True)

    threading.Thread(target=work, daemon=True, name="taskbar-id").start()
