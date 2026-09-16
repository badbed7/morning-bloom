"""Windows Explorer desktop attachment. Never changes the user's wallpaper.

Interactive flower HWNDs are children of the desktop icon view, not floating
top-level overlays. Explorer window classes are not a stable public contract:
fail closed when the host is absent or has an incompatible DPI context.
"""
import ctypes
from ctypes import wintypes
import sys


class DesktopUnavailable(RuntimeError):
    pass


class WindowsDesktopHost:
    def __init__(self):
        if sys.platform != 'win32':
            raise DesktopUnavailable('Windows 바탕화면에서만 사용할 수 있어요.')
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = {
            'EnumWindows': ([self.callback_type, wintypes.LPARAM], wintypes.BOOL),
            'FindWindowExW': ([wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR], wintypes.HWND),
            'GetParent': ([wintypes.HWND], wintypes.HWND),
            'SetParent': ([wintypes.HWND, wintypes.HWND], wintypes.HWND),
            'IsWindow': ([wintypes.HWND], wintypes.BOOL),
            'GetWindowRect': ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            'GetCursorPos': ([ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            'MapWindowPoints': ([wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT], ctypes.c_int),
            'SetWindowPos': ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            'GetWindowDpiAwarenessContext': ([wintypes.HWND], wintypes.HANDLE),
            'AreDpiAwarenessContextsEqual': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'GetSystemMetrics': ([ctypes.c_int], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        suffix = 'PtrW' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'W'
        self.get_style = getattr(self.api, 'GetWindowLong' + suffix)
        self.set_style = getattr(self.api, 'SetWindowLong' + suffix)
        self.get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        self.get_style.restype = ctypes.c_ssize_t
        self.set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.set_style.restype = ctypes.c_ssize_t
        self.styles = {}
        self.parent = self.find_parent()

    def find_parent(self):
        matches = []

        @self.callback_type
        def visit(hwnd, _):
            view = self.api.FindWindowExW(hwnd, None, 'SHELLDLL_DefView', None)
            if view:
                icons = self.api.FindWindowExW(view, None, 'SysListView32', None)
                if icons:
                    matches.append(icons)
            return True

        self.api.EnumWindows(visit, 0)
        if not matches:
            raise DesktopUnavailable('Windows 바탕화면을 찾지 못했어요. 정원은 그대로 보존됩니다.')
        return matches[0]

    def valid(self, hwnd=None):
        return bool(self.api.IsWindow(self.parent) and
                    (hwnd is None or (self.api.IsWindow(hwnd) and self.api.GetParent(hwnd) == self.parent)))

    def position(self, hwnd):
        rect = wintypes.RECT()
        if not self.api.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise DesktopUnavailable('바탕화면 꽃 위치를 읽지 못했어요.')
        return rect.left, rect.top

    def cursor_position(self):
        point = wintypes.POINT()
        self.api.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def attach(self, widget, x, y):
        hwnd = int(widget.winId())
        if not self.valid():
            raise DesktopUnavailable('바탕화면이 다시 시작됐어요. 잠시 후 다시 배치해 주세요.')
        own = self.api.GetWindowDpiAwarenessContext(hwnd)
        shell = self.api.GetWindowDpiAwarenessContext(self.parent)
        if not self.api.AreDpiAwarenessContextsEqual(own, shell):
            raise DesktopUnavailable('현재 Windows 배율 모드가 호환되지 않아 바탕화면 배치를 중단했어요.')
        style = self.get_style(hwnd, -16)
        self.styles[hwnd] = style
        self.set_style(hwnd, -16, (style & ~0x80000000) | 0x40000000)  # POPUP -> CHILD
        ctypes.set_last_error(0)
        self.api.SetParent(hwnd, self.parent)
        if ctypes.get_last_error() or self.api.GetParent(hwnd) != self.parent:
            self.set_style(hwnd, -16, style)
            self.styles.pop(hwnd, None)
            raise DesktopUnavailable('Windows 바탕화면에 꽃을 붙이지 못했어요.')
        self.move(widget, x, y)

    def move(self, widget, x, y):
        hwnd = int(widget.winId())
        if not self.valid(hwnd):
            raise DesktopUnavailable('바탕화면 연결이 끊겼어요.')
        # Stored coordinates are native screen pixels, including negative
        # monitor origins. Keep the flower recoverable after monitor removal.
        rect = wintypes.RECT()
        self.api.GetWindowRect(hwnd, ctypes.byref(rect))
        left, top = self.api.GetSystemMetrics(76), self.api.GetSystemMetrics(77)
        width, height = self.api.GetSystemMetrics(78), self.api.GetSystemMetrics(79)
        x = max(left, min(round(x), left + width - (rect.right - rect.left)))
        y = max(top, min(round(y), top + height - (rect.bottom - rect.top)))
        point = wintypes.POINT(x, y)
        self.api.MapWindowPoints(None, self.parent, ctypes.byref(point), 1)
        if not self.api.SetWindowPos(hwnd, None, point.x, point.y, 0, 0, 0x0001 | 0x0010 | 0x0020):
            raise DesktopUnavailable('바탕화면 꽃을 이동하지 못했어요.')

    def detach(self, widget):
        hwnd = int(widget.winId())
        style = self.styles.pop(hwnd, None)
        widget.hide()
        if style is not None and self.api.IsWindow(hwnd):
            self.api.SetParent(hwnd, None)
            self.set_style(hwnd, -16, style)
