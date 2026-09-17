"""Native positioning for always-on-top Windows flower overlays.

The windows stay independent from Explorer so flowers remain visible above
normal applications. This never changes the wallpaper or desktop icons and
does not install global input hooks.
"""
import ctypes
from ctypes import wintypes
import sys


class DesktopUnavailable(RuntimeError):
    pass


class WindowsDesktopHost:
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040

    def __init__(self):
        if sys.platform != 'win32':
            raise DesktopUnavailable('Windows에서만 플로팅 꽃을 사용할 수 있어요.')
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        signatures = {
            'GetParent': ([wintypes.HWND], wintypes.HWND),
            'IsWindow': ([wintypes.HWND], wintypes.BOOL),
            'GetWindowRect': ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            'GetCursorPos': ([ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            'SetWindowPos': ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            'GetSystemMetrics': ([ctypes.c_int], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        suffix = 'PtrW' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'W'
        self.get_style = getattr(self.api, 'GetWindowLong' + suffix)
        self.get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        self.get_style.restype = ctypes.c_ssize_t
        self.handles = set()

    def valid(self, hwnd=None):
        if hwnd is None:
            return True
        return hwnd in self.handles and bool(self.api.IsWindow(hwnd))

    def position(self, hwnd):
        rect = wintypes.RECT()
        if not self.api.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise DesktopUnavailable('플로팅 꽃 위치를 읽지 못했어요.')
        return rect.left, rect.top

    def cursor_position(self):
        point = wintypes.POINT()
        if not self.api.GetCursorPos(ctypes.byref(point)):
            raise DesktopUnavailable('마우스 위치를 읽지 못했어요.')
        return point.x, point.y

    def attach(self, widget, x, y):
        hwnd = int(widget.winId())
        self.handles.add(hwnd)
        try:
            self.move(widget, x, y)
        except Exception:
            self.handles.discard(hwnd)
            raise

    def move(self, widget, x, y):
        hwnd = int(widget.winId())
        if not self.valid(hwnd):
            raise DesktopUnavailable('플로팅 꽃 창 연결이 끊겼어요.')
        rect = wintypes.RECT()
        if not self.api.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise DesktopUnavailable('플로팅 꽃 크기를 읽지 못했어요.')
        # Stored coordinates are native screen pixels, including negative
        # monitor origins. Clamp to the virtual desktop after monitor removal.
        left, top = self.api.GetSystemMetrics(76), self.api.GetSystemMetrics(77)
        width, height = self.api.GetSystemMetrics(78), self.api.GetSystemMetrics(79)
        window_width = max(1, rect.right - rect.left)
        window_height = max(1, rect.bottom - rect.top)
        x = max(left, min(round(x), left + width - window_width))
        y = max(top, min(round(y), top + height - window_height))
        flags = self.SWP_NOSIZE | self.SWP_NOACTIVATE | self.SWP_SHOWWINDOW
        if not self.api.SetWindowPos(hwnd, self.HWND_TOPMOST, x, y, 0, 0, flags):
            raise DesktopUnavailable('플로팅 꽃을 이동하지 못했어요.')

    def detach(self, widget):
        hwnd = int(widget.winId())
        self.handles.discard(hwnd)
        widget.hide()
        if self.api.IsWindow(hwnd):
            flags = self.SWP_NOSIZE | self.SWP_NOMOVE | self.SWP_NOACTIVATE
            self.api.SetWindowPos(hwnd, self.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
