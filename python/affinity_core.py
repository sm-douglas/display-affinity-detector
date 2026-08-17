"""
affinity_core.py

Core de deteccao de janelas protegidas por SetWindowDisplayAffinity.

IMPORTANTE (limitacao real da API do Windows):
Nao existe um WinEvent (EVENT_OBJECT_*) disparado quando uma aplicacao
chama SetWindowDisplayAffinity. Ou seja, nao da pra "escutar" a mudanca
de affinity diretamente. A estrategia usada aqui e hibrida:

  1. SetWinEventHook nos eventos EVENT_OBJECT_SHOW, EVENT_SYSTEM_FOREGROUND
     e EVENT_OBJECT_CREATE -> reage rapido quando uma janela aparece/muda
     de foco (bom para pegar apps de proctoring/DRM assim que abrem).
  2. Polling leve (thread separada, intervalo configuravel) sobre todas
     as janelas visiveis -> pega mudancas de affinity em janelas que ja
     estavam abertas e nao geraram nenhum WinEvent relevante.

Requisitos: Windows 10 2004+ para WDA_EXCLUDEFROMCAPTURE funcionar
corretamente. So usa a stdlib (ctypes), roda sem dependencias externas.
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import time
from dataclasses import dataclass, asdict
from typing import Callable, Optional

user32 = ctypes.windll.user32

# --- Constantes da API ---
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011

AFFINITY_NAMES = {
    WDA_NONE: "WDA_NONE",
    WDA_MONITOR: "WDA_MONITOR",
    WDA_EXCLUDEFROMCAPTURE: "WDA_EXCLUDEFROMCAPTURE",
}

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_DESTROY = 0x8001
WINEVENT_OUTOFCONTEXT = 0x0000

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
)


@dataclass
class WindowState:
    hwnd: int
    title: str
    pid: int
    affinity: int
    affinity_name: str
    protected: bool
    last_seen: float

    def to_dict(self):
        return asdict(self)


class AffinityMonitor:
    """
    Mantem um estado em memoria de todas as janelas visiveis e seu status
    de display affinity. Thread-safe. Dispara callbacks quando uma janela
    passa a estar protegida ou deixa de estar.
    """

    def __init__(self, poll_interval: float = 1.5):
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._windows: dict[int, WindowState] = {}
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._hook_thread: Optional[threading.Thread] = None
        self._on_change: list[Callable[[WindowState, bool], None]] = []
        self._hook_handles = []

    def on_change(self, callback: Callable[[WindowState, bool], None]):
        """callback(window_state, is_now_protected) toda vez que o status muda."""
        self._on_change.append(callback)

    # --- API publica de leitura ---

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [w.to_dict() for w in self._windows.values()]

    def protected_only(self) -> list[dict]:
        with self._lock:
            return [w.to_dict() for w in self._windows.values() if w.protected]

    def get(self, hwnd: int) -> Optional[dict]:
        with self._lock:
            w = self._windows.get(hwnd)
            return w.to_dict() if w else None

    # --- Consulta individual (reusavel fora do monitor tambem) ---

    @staticmethod
    def query_affinity(hwnd: int) -> Optional[int]:
        affinity = wintypes.DWORD()
        ok = user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity))
        return affinity.value if ok else None

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def get_pid(hwnd: int) -> int:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _refresh_single(self, hwnd: int):
        if not user32.IsWindowVisible(hwnd):
            return
        title = self.get_window_title(hwnd)
        if not title:
            return

        affinity = self.query_affinity(hwnd)
        if affinity is None:
            return

        protected = affinity != WDA_NONE
        name = AFFINITY_NAMES.get(affinity, f"UNKNOWN(0x{affinity:x})")

        state = WindowState(
            hwnd=hwnd,
            title=title,
            pid=self.get_pid(hwnd),
            affinity=affinity,
            affinity_name=name,
            protected=protected,
            last_seen=time.time(),
        )

        with self._lock:
            previous = self._windows.get(hwnd)
            was_protected = previous.protected if previous else False
            self._windows[hwnd] = state

        if protected != was_protected:
            for cb in self._on_change:
                try:
                    cb(state, protected)
                except Exception:
                    pass

    def _full_scan(self):
        def enum_cb(hwnd, lparam):
            self._refresh_single(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # remove janelas que sumiram
        with self._lock:
            alive = {h for h in self._windows if user32.IsWindow(h)}
            for h in list(self._windows):
                if h not in alive:
                    del self._windows[h]

    def _poll_loop(self):
        while self._running:
            self._full_scan()
            time.sleep(self.poll_interval)

    def _win_event_callback(self, hWinEventHook, event, hwnd, idObject,
                             idChild, idEventThread, dwmsEventTime):
        if hwnd:
            self._refresh_single(hwnd)

    def _hook_loop(self):
        cb = WINEVENTPROC(self._win_event_callback)
        events = [
            (EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW),
            (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
            (EVENT_OBJECT_CREATE, EVENT_OBJECT_CREATE),
        ]
        for lo, hi in events:
            handle = user32.SetWinEventHook(
                lo, hi, 0, cb, 0, 0, WINEVENT_OUTOFCONTEXT
            )
            self._hook_handles.append(handle)

        msg = wintypes.MSG()
        while self._running:
            bRet = user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1)
            if bRet:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)

        for handle in self._hook_handles:
            user32.UnhookWinEvent(handle)
        self._hook_handles.clear()

    def start(self):
        if self._running:
            return
        self._running = True
        self._full_scan()  # popula estado inicial de imediato
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._hook_thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._poll_thread.start()
        self._hook_thread.start()

    def stop(self):
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2)
        if self._hook_thread:
            self._hook_thread.join(timeout=2)


if __name__ == "__main__":
    # Modo standalone: so imprime no console, sem API.
    monitor = AffinityMonitor(poll_interval=1.0)

    def print_change(window: WindowState, is_protected: bool):
        status = "PROTEGIDA" if is_protected else "desprotegida"
        print(f"[MUDANCA] '{window.title}' (pid={window.pid}) agora esta {status}")

    monitor.on_change(print_change)
    monitor.start()

    print("Monitorando janelas... Ctrl+C para sair.\n")
    try:
        while True:
            time.sleep(3)
            protected = monitor.protected_only()
            print(f"--- {len(protected)} janela(s) protegida(s) agora ---")
            for w in protected:
                print(f"  {w['title']} (pid={w['pid']}, affinity={w['affinity_name']})")
    except KeyboardInterrupt:
        monitor.stop()
        print("\nEncerrado.")
