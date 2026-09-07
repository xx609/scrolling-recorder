"""Count mouse-wheel events globally on Windows.

Change COUNT_MODE to "down" or "both", then run this file. The program uses
the native Windows low-level mouse hook, so the terminal does not need focus.
The count stays in memory and no active-window or pointer-position data is kept.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from threading import Lock
from typing import Final


# Change this value to "both" to count upward and downward scrolling.
COUNT_MODE = "down"  # Valid values: "down" or "both"

VALID_MODES: Final = frozenset({"down", "both"})
MODE_LABELS: Final = {
    "down": "Down only",
    "both": "Up and down",
}

WH_MOUSE_LL: Final = 14
HC_ACTION: Final = 0
WM_MOUSEWHEEL: Final = 0x020A
WM_QUIT: Final = 0x0012
PM_REMOVE: Final = 0x0001

LRESULT = ctypes.c_ssize_t


class MSLLHOOKSTRUCT(ctypes.Structure):
    """Windows data supplied to a low-level mouse-hook callback."""

    _fields_ = (
        ("point", wintypes.POINT),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    )


def should_count_scroll(vertical_delta: int, mode: str) -> bool:
    """Return whether one vertical scroll event should be counted."""
    if mode == "down":
        return vertical_delta < 0
    if mode == "both":
        return vertical_delta != 0
    return False


class ScrollCounter:
    """Maintain the count safely while hook callbacks are being processed."""

    def __init__(self, mode: str) -> None:
        self._mode = mode
        self._count = 0
        self._lock = Lock()

    def record_scroll(self, vertical_delta: int) -> None:
        if not should_count_scroll(vertical_delta, self._mode):
            return

        with self._lock:
            self._count += 1

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


class WindowsGlobalMouseHook:
    """Install and run a native system-wide Windows mouse hook."""

    def __init__(self, counter: ScrollCounter) -> None:
        if sys.platform != "win32":
            raise OSError("This program supports Windows only.")

        self._counter = counter
        self._hook_handle: int | None = None
        self._callback_error: Exception | None = None

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._hook_proc_type = ctypes.WINFUNCTYPE(
            LRESULT,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        # Keep a strong reference for the lifetime of the installed hook.
        self._hook_proc = self._hook_proc_type(self._mouse_hook_callback)

        self._configure_windows_functions()

    def _configure_windows_functions(self) -> None:
        self._user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            self._hook_proc_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        self._user32.SetWindowsHookExW.restype = wintypes.HANDLE

        self._user32.CallNextHookEx.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._user32.CallNextHookEx.restype = LRESULT

        self._user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        self._user32.PeekMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.PeekMessageW.restype = wintypes.BOOL

        self._user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
        self._user32.TranslateMessage.restype = wintypes.BOOL

        self._user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
        self._user32.DispatchMessageW.restype = LRESULT

        self._kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def _mouse_hook_callback(
        self,
        hook_code: int,
        message: int,
        event_address: int,
    ) -> int:
        if hook_code == HC_ACTION and message == WM_MOUSEWHEEL:
            try:
                event = ctypes.cast(
                    event_address,
                    ctypes.POINTER(MSLLHOOKSTRUCT),
                ).contents
                wheel_word = (event.mouse_data >> 16) & 0xFFFF
                vertical_delta = ctypes.c_short(wheel_word).value
                self._counter.record_scroll(vertical_delta)
            except Exception as error:
                # Never let an exception escape through a native callback.
                self._callback_error = error

        return self._user32.CallNextHookEx(
            self._hook_handle,
            hook_code,
            message,
            event_address,
        )

    def start(self) -> None:
        module_handle = self._kernel32.GetModuleHandleW(None)
        hook_handle = self._user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._hook_proc,
            module_handle,
            0,
        )
        if not hook_handle:
            raise ctypes.WinError(ctypes.get_last_error())

        self._hook_handle = hook_handle

    def run(self) -> None:
        """Pump Windows messages and refresh the display until interrupted."""
        message = wintypes.MSG()
        displayed_count = self._counter.count

        while True:
            while self._user32.PeekMessageW(
                ctypes.byref(message),
                None,
                0,
                0,
                PM_REMOVE,
            ):
                if message.message == WM_QUIT:
                    return
                self._user32.TranslateMessage(ctypes.byref(message))
                self._user32.DispatchMessageW(ctypes.byref(message))

            if self._callback_error is not None:
                error = self._callback_error
                self._callback_error = None
                raise RuntimeError("Mouse-hook callback failed") from error

            current_count = self._counter.count
            if current_count != displayed_count:
                print(f"\rCount: {current_count}", end="", flush=True)
                displayed_count = current_count

            # A short pause keeps CPU use low while still updating promptly.
            time.sleep(0.01)

    def stop(self) -> None:
        if self._hook_handle is None:
            return

        hook_handle = self._hook_handle
        self._hook_handle = None
        if not self._user32.UnhookWindowsHookEx(hook_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self) -> WindowsGlobalMouseHook:
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


def validate_mode(mode: str) -> bool:
    if mode in VALID_MODES:
        return True

    choices = ", ".join(f'"{choice}"' for choice in sorted(VALID_MODES))
    print(
        f'Error: COUNT_MODE is set to "{mode}". Valid values are {choices}.',
        file=sys.stderr,
    )
    return False


def main() -> int:
    if not validate_mode(COUNT_MODE):
        return 2

    if sys.platform != "win32":
        print("Error: This program supports Windows only.", file=sys.stderr)
        return 1

    counter = ScrollCounter(COUNT_MODE)

    print("Mouse Scroll Counter")
    print(f"Mode: {MODE_LABELS[COUNT_MODE]}")
    print("Listening globally. The terminal does not need focus.")
    print("Press Ctrl+C to stop.")
    print("Count: 0", end="", flush=True)

    exit_code = 0
    try:
        with WindowsGlobalMouseHook(counter) as hook:
            hook.run()
    except KeyboardInterrupt:
        pass
    except PermissionError as error:
        print(
            "\nError: Windows denied access to global mouse input. "
            "Try running the terminal as Administrator if you need to count "
            "inside elevated applications.",
            file=sys.stderr,
        )
        print(f"Details: {error}", file=sys.stderr)
        exit_code = 1
    except OSError as error:
        print(
            "\nError: Windows could not install the global mouse hook. "
            "Security software or permissions may be blocking it.",
            file=sys.stderr,
        )
        print(f"Details: {error}", file=sys.stderr)
        exit_code = 1
    except Exception as error:
        print(f"\nError: The global mouse hook stopped unexpectedly: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        print(f"\rFinal count: {counter.count}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
