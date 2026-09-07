"""Count normalized vertical scroll distance globally on Windows.

The script receives physical mouse-wheel reports and Precision Touchpad contact
reports through Windows Raw Input. Change COUNT_MODE to "down" or "both".
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from threading import Lock
from typing import Final


# Change this value to "both" to count upward and downward scrolling.
COUNT_MODE = "down"  # Valid values: "down" or "both"

VALID_MODES: Final = frozenset({"down", "both"})
MODE_LABELS: Final = {"down": "Down only", "both": "Up and down"}

# Windows constants
WM_INPUT: Final = 0x00FF
WM_DESTROY: Final = 0x0002
WM_QUIT: Final = 0x0012
PM_REMOVE: Final = 0x0001
RID_INPUT: Final = 0x10000003
RIDI_PREPARSEDDATA: Final = 0x20000005
RIM_TYPEMOUSE: Final = 0
RIM_TYPEHID: Final = 2
RI_MOUSE_WHEEL: Final = 0x0400
RIDEV_REMOVE: Final = 0x00000001
RIDEV_INPUTSINK: Final = 0x00000100
HID_USAGE_PAGE_GENERIC: Final = 0x01
HID_USAGE_GENERIC_MOUSE: Final = 0x02
HID_USAGE_PAGE_DIGITIZER: Final = 0x0D
HID_USAGE_DIGITIZER_TOUCHPAD: Final = 0x05
HID_USAGE_DIGITIZER_TIP_SWITCH: Final = 0x42
HID_USAGE_DIGITIZER_CONTACT_ID: Final = 0x51
HID_USAGE_DIGITIZER_CONTACT_COUNT: Final = 0x54
HID_USAGE_DIGITIZER_SCAN_TIME: Final = 0x56
HID_USAGE_GENERIC_X: Final = 0x30
HID_USAGE_GENERIC_Y: Final = 0x31
HIDP_REPORT_TYPE_INPUT: Final = 0
HIDP_STATUS_SUCCESS: Final = 0x00110000
UINT_ERROR: Final = 0xFFFFFFFF
WHEEL_DELTA: Final = 120
SPI_GETWHEELSCROLLLINES: Final = 0x0068
WHEEL_PAGESCROLL: Final = 0xFFFFFFFF
SM_CYSCREEN: Final = 1
DEFAULT_DPI: Final = 96
DEFAULT_SCROLL_LINES: Final = 3
DEFAULT_LINE_HEIGHT_AT_96_DPI: Final = 16.0

LRESULT = ctypes.c_ssize_t
WINDOW_PROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = (
        ("usage_page", wintypes.USHORT),
        ("usage", wintypes.USHORT),
        ("flags", wintypes.DWORD),
        ("target_window", wintypes.HWND),
    )


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("size", wintypes.DWORD),
        ("device", wintypes.HANDLE),
        ("parameter", wintypes.WPARAM),
    )


class RAWMOUSEBUTTONDATA(ctypes.Structure):
    _fields_ = (
        ("button_flags", wintypes.USHORT),
        ("button_data", wintypes.USHORT),
    )


class RAWMOUSEBUTTONS(ctypes.Union):
    _anonymous_ = ("data",)
    _fields_ = (("data", RAWMOUSEBUTTONDATA), ("buttons", wintypes.ULONG))


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("button_union",)
    _fields_ = (
        ("flags", wintypes.USHORT),
        ("button_union", RAWMOUSEBUTTONS),
        ("raw_buttons", wintypes.ULONG),
        ("last_x", wintypes.LONG),
        ("last_y", wintypes.LONG),
        ("extra_information", wintypes.ULONG),
    )


class RAWINPUTMOUSE(ctypes.Structure):
    _fields_ = (("header", RAWINPUTHEADER), ("mouse", RAWMOUSE))


class RAWHIDHEADER(ctypes.Structure):
    _fields_ = (("report_size", wintypes.DWORD), ("report_count", wintypes.DWORD))


class HIDP_CAPS(ctypes.Structure):
    _fields_ = (
        ("usage", wintypes.USHORT),
        ("usage_page", wintypes.USHORT),
        ("input_report_byte_length", wintypes.USHORT),
        ("output_report_byte_length", wintypes.USHORT),
        ("feature_report_byte_length", wintypes.USHORT),
        ("reserved", wintypes.USHORT * 17),
        ("number_link_collection_nodes", wintypes.USHORT),
        ("number_input_button_caps", wintypes.USHORT),
        ("number_input_value_caps", wintypes.USHORT),
        ("number_input_data_indices", wintypes.USHORT),
        ("number_output_button_caps", wintypes.USHORT),
        ("number_output_value_caps", wintypes.USHORT),
        ("number_output_data_indices", wintypes.USHORT),
        ("number_feature_button_caps", wintypes.USHORT),
        ("number_feature_value_caps", wintypes.USHORT),
        ("number_feature_data_indices", wintypes.USHORT),
    )


class HIDP_CAPS_RANGE(ctypes.Structure):
    _fields_ = tuple(
        (name, wintypes.USHORT)
        for name in (
            "usage_min",
            "usage_max",
            "string_min",
            "string_max",
            "designator_min",
            "designator_max",
            "data_index_min",
            "data_index_max",
        )
    )


class HIDP_CAPS_NOT_RANGE(ctypes.Structure):
    _fields_ = tuple(
        (name, wintypes.USHORT)
        for name in (
            "usage",
            "reserved1",
            "string_index",
            "reserved2",
            "designator_index",
            "reserved3",
            "data_index",
            "reserved4",
        )
    )


class HIDP_CAPS_UNION(ctypes.Union):
    _fields_ = (("range", HIDP_CAPS_RANGE), ("not_range", HIDP_CAPS_NOT_RANGE))


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = (
        ("usage_page", wintypes.USHORT),
        ("report_id", ctypes.c_ubyte),
        ("is_alias", ctypes.c_ubyte),
        ("bit_field", wintypes.USHORT),
        ("link_collection", wintypes.USHORT),
        ("link_usage", wintypes.USHORT),
        ("link_usage_page", wintypes.USHORT),
        ("is_range", ctypes.c_ubyte),
        ("is_string_range", ctypes.c_ubyte),
        ("is_designator_range", ctypes.c_ubyte),
        ("is_absolute", ctypes.c_ubyte),
        ("has_null", ctypes.c_ubyte),
        ("reserved", ctypes.c_ubyte),
        ("bit_size", wintypes.USHORT),
        ("report_count", wintypes.USHORT),
        ("reserved2", wintypes.USHORT * 5),
        ("units_exp", wintypes.ULONG),
        ("units", wintypes.ULONG),
        ("logical_min", wintypes.LONG),
        ("logical_max", wintypes.LONG),
        ("physical_min", wintypes.LONG),
        ("physical_max", wintypes.LONG),
        ("selection", HIDP_CAPS_UNION),
    )


class WNDCLASSW(ctypes.Structure):
    _fields_ = (
        ("style", wintypes.UINT),
        ("window_proc", WINDOW_PROC),
        ("class_extra", ctypes.c_int),
        ("window_extra", ctypes.c_int),
        ("instance", wintypes.HINSTANCE),
        ("icon", wintypes.HANDLE),
        ("cursor", wintypes.HANDLE),
        ("background", wintypes.HANDLE),
        ("menu_name", wintypes.LPCWSTR),
        ("class_name", wintypes.LPCWSTR),
    )


@dataclass(frozen=True)
class HidValueSpec:
    usage_page: int
    usage: int
    link_collection: int
    logical_min: int
    logical_max: int
    physical_min: int
    physical_max: int
    units: int
    units_exp: int


@dataclass(frozen=True)
class TouchpadContactReport:
    scan_time: int
    contact_count: int
    contact_id: int
    x: int
    y: int
    touching: bool


def _hid_status(status: int) -> int:
    return status & UINT_ERROR


def _usage_for_capability(capability: HIDP_VALUE_CAPS) -> tuple[int, int]:
    if capability.is_range:
        return (
            capability.selection.range.usage_min,
            capability.selection.range.usage_max,
        )
    usage = capability.selection.not_range.usage
    return usage, usage


class PixelCounter:
    """Accumulate a monotonic pixel total using the selected direction mode."""

    def __init__(self, mode: str) -> None:
        self._mode = mode
        self._total = 0.0
        self._lock = Lock()

    def record_content_movement(self, signed_pixels: float) -> None:
        """Record content motion where positive means scrolling down."""
        if self._mode == "down":
            amount = signed_pixels if signed_pixels > 0 else 0.0
        else:
            amount = abs(signed_pixels)

        if amount == 0:
            return

        with self._lock:
            self._total += amount

    @property
    def pixels(self) -> int:
        with self._lock:
            return int(round(self._total))

    @property
    def precise_pixels(self) -> float:
        with self._lock:
            return self._total


class PixelNormalizer:
    """Convert hardware-specific movement into normalized display pixels."""

    def __init__(self, user32: ctypes.WinDLL) -> None:
        self.dpi = self._get_system_dpi(user32)
        self.mouse_pixels_per_notch = self._get_mouse_pixels_per_notch(user32)

    @staticmethod
    def _get_system_dpi(user32: ctypes.WinDLL) -> int:
        get_dpi = getattr(user32, "GetDpiForSystem", None)
        if get_dpi is None:
            return DEFAULT_DPI
        get_dpi.argtypes = ()
        get_dpi.restype = wintypes.UINT
        return int(get_dpi()) or DEFAULT_DPI

    def _get_mouse_pixels_per_notch(self, user32: ctypes.WinDLL) -> float:
        scroll_lines = wintypes.UINT(DEFAULT_SCROLL_LINES)
        user32.SystemParametersInfoW.argtypes = (
            wintypes.UINT,
            wintypes.UINT,
            wintypes.LPVOID,
            wintypes.UINT,
        )
        user32.SystemParametersInfoW.restype = wintypes.BOOL
        user32.SystemParametersInfoW(
            SPI_GETWHEELSCROLLLINES,
            0,
            ctypes.byref(scroll_lines),
            0,
        )

        if scroll_lines.value == WHEEL_PAGESCROLL:
            user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
            user32.GetSystemMetrics.restype = ctypes.c_int
            return float(max(user32.GetSystemMetrics(SM_CYSCREEN), 1))

        line_height = DEFAULT_LINE_HEIGHT_AT_96_DPI * self.dpi / DEFAULT_DPI
        return float(scroll_lines.value) * line_height

    def mouse_wheel_to_pixels(self, wheel_delta: int) -> float:
        # Windows uses positive wheel values for up and negative values for down.
        return -(wheel_delta / WHEEL_DELTA) * self.mouse_pixels_per_notch

    def touchpad_axis_pixels_per_unit(self, specification: HidValueSpec) -> float:
        logical_span = specification.logical_max - specification.logical_min
        physical_span = specification.physical_max - specification.physical_min

        # HID unit system 1 is SI Linear; length is expressed in centimeters.
        unit_system = specification.units & 0xF
        exponent = specification.units_exp & 0xF
        if exponent >= 8:
            exponent -= 16

        if logical_span and physical_span and unit_system == 1:
            centimeters_per_unit = (physical_span * (10.0**exponent)) / logical_span
            inches_per_unit = centimeters_per_unit / 2.54
            scale = abs(inches_per_unit * self.dpi)
            if scale > 0:
                return scale

        # Precision touchpads must provide at least 300 logical units per inch.
        return self.dpi / 300.0


class PrecisionTouchpadParser:
    """Decode standard Precision Touchpad HID input reports."""

    def __init__(
        self,
        user32: ctypes.WinDLL,
        hid: ctypes.WinDLL,
        device_handle: int,
        normalizer: PixelNormalizer,
    ) -> None:
        self._user32 = user32
        self._hid = hid
        self._device_handle = device_handle
        self._preparsed_data = self._load_preparsed_data()
        self._caps = self._load_caps()
        self._value_specs = self._load_value_specs()

        self._contact_id = self._require_spec(
            HID_USAGE_PAGE_DIGITIZER, HID_USAGE_DIGITIZER_CONTACT_ID
        )
        self._contact_count = self._require_spec(
            HID_USAGE_PAGE_DIGITIZER, HID_USAGE_DIGITIZER_CONTACT_COUNT
        )
        self._scan_time = self._require_spec(
            HID_USAGE_PAGE_DIGITIZER, HID_USAGE_DIGITIZER_SCAN_TIME
        )
        self._x = self._require_spec(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_X)
        self._y = self._require_spec(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_Y)

        self.x_pixels_per_unit = normalizer.touchpad_axis_pixels_per_unit(self._x)
        self.y_pixels_per_unit = normalizer.touchpad_axis_pixels_per_unit(self._y)

    @property
    def report_length(self) -> int:
        return self._caps.input_report_byte_length

    def _load_preparsed_data(self):
        size = wintypes.UINT(0)
        result = self._user32.GetRawInputDeviceInfoW(
            self._device_handle,
            RIDI_PREPARSEDDATA,
            None,
            ctypes.byref(size),
        )
        if result == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())

        buffer = ctypes.create_string_buffer(size.value)
        result = self._user32.GetRawInputDeviceInfoW(
            self._device_handle,
            RIDI_PREPARSEDDATA,
            buffer,
            ctypes.byref(size),
        )
        if result == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer

    def _load_caps(self) -> HIDP_CAPS:
        caps = HIDP_CAPS()
        status = _hid_status(self._hid.HidP_GetCaps(self._preparsed_data, ctypes.byref(caps)))
        if status != HIDP_STATUS_SUCCESS:
            raise OSError(f"HidP_GetCaps failed with status 0x{status:08X}")
        return caps

    def _load_value_specs(self) -> list[HidValueSpec]:
        count = wintypes.USHORT(self._caps.number_input_value_caps)
        capabilities = (HIDP_VALUE_CAPS * count.value)()
        status = _hid_status(
            self._hid.HidP_GetValueCaps(
                HIDP_REPORT_TYPE_INPUT,
                capabilities,
                ctypes.byref(count),
                self._preparsed_data,
            )
        )
        if status != HIDP_STATUS_SUCCESS:
            raise OSError(f"HidP_GetValueCaps failed with status 0x{status:08X}")

        specs: list[HidValueSpec] = []
        for capability in capabilities[: count.value]:
            usage_min, usage_max = _usage_for_capability(capability)
            for usage in range(usage_min, usage_max + 1):
                specs.append(
                    HidValueSpec(
                        usage_page=capability.usage_page,
                        usage=usage,
                        link_collection=capability.link_collection,
                        logical_min=capability.logical_min,
                        logical_max=capability.logical_max,
                        physical_min=capability.physical_min,
                        physical_max=capability.physical_max,
                        units=capability.units,
                        units_exp=capability.units_exp,
                    )
                )
        return specs

    def _require_spec(self, usage_page: int, usage: int) -> HidValueSpec:
        for specification in self._value_specs:
            if specification.usage_page == usage_page and specification.usage == usage:
                return specification
        raise OSError(
            f"Touchpad is missing HID usage page 0x{usage_page:02X}, usage 0x{usage:02X}"
        )

    def _get_value(self, specification: HidValueSpec, report_buffer, report_length: int) -> int:
        value = wintypes.ULONG(0)
        status = _hid_status(
            self._hid.HidP_GetUsageValue(
                HIDP_REPORT_TYPE_INPUT,
                specification.usage_page,
                specification.link_collection,
                specification.usage,
                ctypes.byref(value),
                self._preparsed_data,
                report_buffer,
                report_length,
            )
        )
        if status != HIDP_STATUS_SUCCESS:
            raise OSError(
                f"HidP_GetUsageValue failed for usage 0x{specification.usage:02X} "
                f"with status 0x{status:08X}"
            )
        return int(value.value)

    def _is_touching(self, report_buffer, report_length: int) -> bool:
        usages = (wintypes.USHORT * 16)()
        usage_count = wintypes.ULONG(len(usages))
        status = _hid_status(
            self._hid.HidP_GetUsages(
                HIDP_REPORT_TYPE_INPUT,
                HID_USAGE_PAGE_DIGITIZER,
                self._contact_id.link_collection,
                usages,
                ctypes.byref(usage_count),
                self._preparsed_data,
                report_buffer,
                report_length,
            )
        )
        if status != HIDP_STATUS_SUCCESS:
            raise OSError(f"HidP_GetUsages failed with status 0x{status:08X}")
        return HID_USAGE_DIGITIZER_TIP_SWITCH in usages[: usage_count.value]

    def parse(self, report: bytes) -> TouchpadContactReport:
        if len(report) != self.report_length:
            raise OSError(
                f"Unexpected touchpad report length {len(report)}; "
                f"expected {self.report_length}"
            )

        report_buffer = ctypes.create_string_buffer(report, len(report))
        return TouchpadContactReport(
            scan_time=self._get_value(self._scan_time, report_buffer, len(report)),
            contact_count=self._get_value(self._contact_count, report_buffer, len(report)),
            contact_id=self._get_value(self._contact_id, report_buffer, len(report)),
            x=self._get_value(self._x, report_buffer, len(report)),
            y=self._get_value(self._y, report_buffer, len(report)),
            touching=self._is_touching(report_buffer, len(report)),
        )


class TouchpadGestureTracker:
    """Turn standard two-finger touchpad frames into vertical pixel motion."""

    def __init__(
        self,
        counter: PixelCounter,
        x_pixels_per_unit: float,
        y_pixels_per_unit: float,
    ) -> None:
        self._counter = counter
        self._x_scale = x_pixels_per_unit
        self._y_scale = y_pixels_per_unit
        self._pending_scan: int | None = None
        self._pending_expected = 0
        self._pending_seen = 0
        self._pending_contacts: dict[int, tuple[float, float]] = {}
        self._previous_ids: frozenset[int] | None = None
        self._previous_centroid: tuple[float, float] | None = None

    def add_report(self, report: TouchpadContactReport) -> None:
        if self._pending_scan is not None and report.scan_time != self._pending_scan:
            self._finish_frame()

        if self._pending_scan is None:
            self._pending_scan = report.scan_time
            self._pending_expected = report.contact_count
            self._pending_seen = 0
            self._pending_contacts = {}

        self._pending_expected = max(self._pending_expected, report.contact_count)
        self._pending_seen += 1
        if report.touching:
            self._pending_contacts[report.contact_id] = (
                report.x * self._x_scale,
                report.y * self._y_scale,
            )

        if self._pending_expected == 0 or self._pending_seen >= self._pending_expected:
            self._finish_frame()

    def flush(self) -> None:
        if self._pending_scan is not None:
            self._finish_frame()

    def _finish_frame(self) -> None:
        contacts = self._pending_contacts
        self._pending_scan = None
        self._pending_expected = 0
        self._pending_seen = 0
        self._pending_contacts = {}

        if len(contacts) != 2:
            self._previous_ids = None
            self._previous_centroid = None
            return

        contact_ids = frozenset(contacts)
        centroid_x = sum(point[0] for point in contacts.values()) / 2.0
        centroid_y = sum(point[1] for point in contacts.values()) / 2.0

        if self._previous_ids == contact_ids and self._previous_centroid is not None:
            delta_x = centroid_x - self._previous_centroid[0]
            delta_y = centroid_y - self._previous_centroid[1]

            # A two-finger pan is vertical only when vertical motion dominates.
            if delta_y and abs(delta_y) >= abs(delta_x):
                # Moving fingers upward moves content toward later/down content.
                self._counter.record_content_movement(-delta_y)

        self._previous_ids = contact_ids
        self._previous_centroid = (centroid_x, centroid_y)


class WindowsInputReceiver:
    """Receive physical mouse and Precision Touchpad data in the background."""

    def __init__(self, counter: PixelCounter) -> None:
        if sys.platform != "win32":
            raise OSError("This program supports Windows only.")

        self._counter = counter
        self._window_handle: int | None = None
        self._module_handle: int | None = None
        self._class_name = f"ScrollPixelCounter_{id(self)}"
        self._callback_error: Exception | None = None
        self._touchpads: dict[int, tuple[PrecisionTouchpadParser, TouchpadGestureTracker]] = {}

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._hid = ctypes.WinDLL("hid", use_last_error=True)
        self._window_proc = WINDOW_PROC(self._handle_window_message)
        self._configure_functions()
        self._normalizer = PixelNormalizer(self._user32)

    def _configure_functions(self) -> None:
        self._user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
        self._user32.RegisterClassW.restype = wintypes.WORD
        self._user32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
        self._user32.UnregisterClassW.restype = wintypes.BOOL
        self._user32.CreateWindowExW.argtypes = (
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HANDLE,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        )
        self._user32.CreateWindowExW.restype = wintypes.HWND
        self._user32.DestroyWindow.argtypes = (wintypes.HWND,)
        self._user32.DestroyWindow.restype = wintypes.BOOL
        self._user32.DefWindowProcW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._user32.DefWindowProcW.restype = LRESULT
        self._user32.PostQuitMessage.argtypes = (ctypes.c_int,)
        self._user32.PostQuitMessage.restype = None
        self._user32.RegisterRawInputDevices.argtypes = (
            ctypes.POINTER(RAWINPUTDEVICE),
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.RegisterRawInputDevices.restype = wintypes.BOOL
        self._user32.GetRawInputData.argtypes = (
            wintypes.HANDLE,
            wintypes.UINT,
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.UINT),
            wintypes.UINT,
        )
        self._user32.GetRawInputData.restype = wintypes.UINT
        self._user32.GetRawInputDeviceInfoW.argtypes = (
            wintypes.HANDLE,
            wintypes.UINT,
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.UINT),
        )
        self._user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
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

        self._hid.HidP_GetCaps.argtypes = (wintypes.LPVOID, ctypes.POINTER(HIDP_CAPS))
        self._hid.HidP_GetCaps.restype = wintypes.LONG
        self._hid.HidP_GetValueCaps.argtypes = (
            ctypes.c_int,
            ctypes.POINTER(HIDP_VALUE_CAPS),
            ctypes.POINTER(wintypes.USHORT),
            wintypes.LPVOID,
        )
        self._hid.HidP_GetValueCaps.restype = wintypes.LONG
        self._hid.HidP_GetUsageValue.argtypes = (
            ctypes.c_int,
            wintypes.USHORT,
            wintypes.USHORT,
            wintypes.USHORT,
            ctypes.POINTER(wintypes.ULONG),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.ULONG,
        )
        self._hid.HidP_GetUsageValue.restype = wintypes.LONG
        self._hid.HidP_GetUsages.argtypes = (
            ctypes.c_int,
            wintypes.USHORT,
            wintypes.USHORT,
            ctypes.POINTER(wintypes.USHORT),
            ctypes.POINTER(wintypes.ULONG),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.ULONG,
        )
        self._hid.HidP_GetUsages.restype = wintypes.LONG

    def _handle_window_message(
        self,
        window: int,
        message: int,
        word_parameter: int,
        long_parameter: int,
    ) -> int:
        if message == WM_INPUT:
            try:
                self._handle_raw_input(long_parameter)
            except Exception as error:
                self._callback_error = error
        elif message == WM_DESTROY:
            self._user32.PostQuitMessage(0)
            return 0

        return self._user32.DefWindowProcW(
            window, message, word_parameter, long_parameter
        )

    def _read_raw_input(self, raw_input_handle: int):
        data_size = wintypes.UINT(0)
        result = self._user32.GetRawInputData(
            raw_input_handle,
            RID_INPUT,
            None,
            ctypes.byref(data_size),
            ctypes.sizeof(RAWINPUTHEADER),
        )
        if result == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())

        buffer = ctypes.create_string_buffer(data_size.value)
        result = self._user32.GetRawInputData(
            raw_input_handle,
            RID_INPUT,
            buffer,
            ctypes.byref(data_size),
            ctypes.sizeof(RAWINPUTHEADER),
        )
        if result == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer

    def _handle_raw_input(self, raw_input_handle: int) -> None:
        buffer = self._read_raw_input(raw_input_handle)
        header = ctypes.cast(buffer, ctypes.POINTER(RAWINPUTHEADER)).contents

        if header.type == RIM_TYPEMOUSE:
            raw_mouse = ctypes.cast(buffer, ctypes.POINTER(RAWINPUTMOUSE)).contents.mouse
            if raw_mouse.button_flags & RI_MOUSE_WHEEL:
                wheel_delta = ctypes.c_short(raw_mouse.button_data).value
                pixels = self._normalizer.mouse_wheel_to_pixels(wheel_delta)
                self._counter.record_content_movement(pixels)
            return

        if header.type != RIM_TYPEHID or not header.device:
            return

        device_key = int(header.device)
        if device_key not in self._touchpads:
            parser = PrecisionTouchpadParser(
                self._user32,
                self._hid,
                device_key,
                self._normalizer,
            )
            tracker = TouchpadGestureTracker(
                self._counter,
                parser.x_pixels_per_unit,
                parser.y_pixels_per_unit,
            )
            self._touchpads[device_key] = parser, tracker

        parser, tracker = self._touchpads[device_key]
        raw_hid_offset = ctypes.sizeof(RAWINPUTHEADER)
        raw_hid = ctypes.cast(
            ctypes.addressof(buffer) + raw_hid_offset,
            ctypes.POINTER(RAWHIDHEADER),
        ).contents
        reports_offset = raw_hid_offset + ctypes.sizeof(RAWHIDHEADER)
        raw_bytes = buffer.raw

        for index in range(raw_hid.report_count):
            start = reports_offset + index * raw_hid.report_size
            end = start + raw_hid.report_size
            if end > len(raw_bytes):
                raise OSError("Raw touchpad report extends past its input buffer")
            tracker.add_report(parser.parse(raw_bytes[start:end]))

    def start(self) -> None:
        module_handle = self._kernel32.GetModuleHandleW(None)
        if not module_handle:
            raise ctypes.WinError(ctypes.get_last_error())

        window_class = WNDCLASSW()
        window_class.window_proc = self._window_proc
        window_class.instance = module_handle
        window_class.class_name = self._class_name
        if not self._user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())

        self._module_handle = module_handle
        window_handle = self._user32.CreateWindowExW(
            0,
            self._class_name,
            "Scroll Pixel Counter Input Receiver",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            module_handle,
            None,
        )
        if not window_handle:
            self._unregister_window_class()
            raise ctypes.WinError(ctypes.get_last_error())
        self._window_handle = window_handle

        devices = (RAWINPUTDEVICE * 2)(
            RAWINPUTDEVICE(
                HID_USAGE_PAGE_GENERIC,
                HID_USAGE_GENERIC_MOUSE,
                RIDEV_INPUTSINK,
                window_handle,
            ),
            RAWINPUTDEVICE(
                HID_USAGE_PAGE_DIGITIZER,
                HID_USAGE_DIGITIZER_TOUCHPAD,
                RIDEV_INPUTSINK,
                window_handle,
            ),
        )
        if not self._user32.RegisterRawInputDevices(
            devices, len(devices), ctypes.sizeof(RAWINPUTDEVICE)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.stop()
            raise error

    def run(self) -> None:
        message = wintypes.MSG()
        displayed_pixels = self._counter.pixels

        while True:
            while self._user32.PeekMessageW(
                ctypes.byref(message), None, 0, 0, PM_REMOVE
            ):
                if message.message == WM_QUIT:
                    return
                self._user32.TranslateMessage(ctypes.byref(message))
                self._user32.DispatchMessageW(ctypes.byref(message))

            if self._callback_error is not None:
                error = self._callback_error
                self._callback_error = None
                raise RuntimeError("Windows input processing failed") from error

            current_pixels = self._counter.pixels
            if current_pixels != displayed_pixels:
                print(f"\rPixels: {current_pixels}", end="", flush=True)
                displayed_pixels = current_pixels

            time.sleep(0.005)

    def _unregister_window_class(self) -> None:
        if self._module_handle is not None:
            module_handle = self._module_handle
            self._module_handle = None
            self._user32.UnregisterClassW(self._class_name, module_handle)

    def stop(self) -> None:
        if self._window_handle is not None:
            devices = (RAWINPUTDEVICE * 2)(
                RAWINPUTDEVICE(
                    HID_USAGE_PAGE_GENERIC,
                    HID_USAGE_GENERIC_MOUSE,
                    RIDEV_REMOVE,
                    None,
                ),
                RAWINPUTDEVICE(
                    HID_USAGE_PAGE_DIGITIZER,
                    HID_USAGE_DIGITIZER_TOUCHPAD,
                    RIDEV_REMOVE,
                    None,
                ),
            )
            self._user32.RegisterRawInputDevices(
                devices, len(devices), ctypes.sizeof(RAWINPUTDEVICE)
            )

            window_handle = self._window_handle
            self._window_handle = None
            self._user32.DestroyWindow(window_handle)

        self._unregister_window_class()

    def __enter__(self) -> WindowsInputReceiver:
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

    counter = PixelCounter(COUNT_MODE)
    print("Global Mouse + Precision Touchpad Scroll Counter")
    print(f"Mode: {MODE_LABELS[COUNT_MODE]}")
    print("Unit: normalized display pixels")
    print("Press Ctrl+C to stop.")
    print("Pixels: 0", end="", flush=True)

    exit_code = 0
    try:
        with WindowsInputReceiver(counter) as receiver:
            receiver.run()
    except KeyboardInterrupt:
        pass
    except OSError as error:
        print(f"\nError: Windows input registration failed: {error}", file=sys.stderr)
        exit_code = 1
    except Exception as error:
        cause = error.__cause__ or error
        print(f"\nError: Input receiver stopped unexpectedly: {cause}", file=sys.stderr)
        exit_code = 1
    finally:
        print(f"\rFinal pixels: {counter.pixels}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
