# -*- coding: utf-8 -*-
"""
Fireball proxy module.

Прозрачный прокси сообщений Windows между "Атом" (источник) и "Генератор токла" (целевой),
при этом прокси представляется под именем/классом оригинального генератора тока
и передает команды START/STOP в очередь для обработки в GUI-потоке.

Нужные библиотеки: pywin32 (win32gui, win32api, win32con)
"""
from __future__ import annotations
import time
import threading
import pythoncom
import logging
from typing import Optional, Dict
from queue import Queue
import win32gui
import win32con
import win32api

# FIXME логер может не работать, закоментил
#  Настройка логгера
# logger = logging.getLogger("FireballProxy")
# logger.setLevel(logging.NOTSET)
# if not logger.handlers:
#     ch = logging.StreamHandler()
#     ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
#     logger.addHandler(ch)

# Диапазон пользовательских сообщений
WM_USER = 0x0400

# Сообщения Fireball
WM_FIREBALL_START = WM_USER + 1
WM_FIREBALL_STOP = WM_USER + 2
WM_FIREBALL_SETTINGS = WM_USER + 3
WM_FIREBALL_NOTIFY = WM_USER + 4
WM_FIREBALL_PARAMS = WM_USER + 5
WM_FIREBALL_LOAD_REGIME = WM_USER + 10
WM_FIREBALL_SET_STEP_TIME = WM_USER + 11
WM_FIREBALL_GET_STEPS_NUM = WM_USER + 12
WM_FIREBALL_GET_XML = WM_USER + 22
WM_FIREBALL_GET_GRAPHICS = WM_USER + 23

# Резервные ответы, если целевой процесс не найден
DEFAULT_RESPONSES: Dict[int, int] = {
    WM_FIREBALL_START: 1,
    WM_FIREBALL_STOP: 1,
    WM_FIREBALL_LOAD_REGIME: 1,
    WM_FIREBALL_GET_XML: 0,
    WM_FIREBALL_GET_GRAPHICS: 0,
}


class FireballProxy:
    """Прокси сообщений между Атомом и Генератором тока."""

    def __init__(
        self,
        claim_class: str,
        claim_name: str,
        forward_name: str,
        command_queue: Queue,
        send_timeout_ms: int = 5000,
        find_interval_sec: float = 1.0,
    ):
        self.claim_class = claim_class
        self.claim_name = claim_name
        self.forward_name = forward_name
        self.command_queue = command_queue
        self.send_timeout_ms = send_timeout_ms
        self.find_interval_sec = find_interval_sec

        self._target_hwnd: Optional[int] = None
        self._last_find_time = 0.0
        self.hwnd_proxy: Optional[int] = None
        self._running = False
        self._pump_thread: Optional[threading.Thread] = None
        self._reg_lock = threading.Lock()

        # logger.debug("FireballProxy инициализирован (mask='%s', forward='%s')", claim_name, forward_name)

    # ---------- Публичные методы ----------

    def start(self) -> None:
        """Создать окно и запустить цикл сообщений."""
        with self._reg_lock:
            if self._running:
                # logger.warning("Попытка повторного запуска прокси проигнорирована.")
                return
            self._create_window()
            self._running = True
            self._pump_thread = threading.Thread(target=self._pump_messages, daemon=True)
            self._pump_thread.start()
            # logger.info("FireballProxy запущен. HWND=%s", self.hwnd_proxy)

    def stop(self) -> None:
        """Остановить прокси и уничтожить окно."""
        with self._reg_lock:
            self._running = False
            if self.hwnd_proxy:
                # logger.info("Останавливаю FireballProxy и закрываю окно...")
                try:
                    win32gui.PostMessage(self.hwnd_proxy, win32con.WM_CLOSE, 0, 0)
                except Exception as e:
                    # logger.warning("Ошибка при закрытии окна: %s", e)
                    pass
                self.hwnd_proxy = None

    # ---------- Внутренние методы ----------

    def _create_window(self) -> None:
        """Регистрирует класс и создаёт скрытое окно."""
        wc = win32gui.WNDCLASS()
        wc.lpszClassName = self.claim_class
        wc.lpfnWndProc = self._wnd_proc
        wc.hInstance = win32api.GetModuleHandle(None)
        try:
            win32gui.RegisterClass(wc)
        except Exception:
            pass

        self.hwnd_proxy = win32gui.CreateWindowEx(
            0, self.claim_class, self.claim_name,
            0,
            0, 0, 1, 1,
            0, 0, wc.hInstance, None
        )
        # logger.debug("Создано окно-клон '%s' (HWND=%s)", self.claim_name, self.hwnd_proxy)

    def _pump_messages(self) -> None:
        """Цикл сообщений. Запускается в отдельном потоке."""
        pythoncom.CoInitialize()
        try:
            while self._running:
                try:
                    win32gui.PumpWaitingMessages()
                except Exception as e:
                    # logger.exception(f"[FireballProxy] Pump error: {e}")
                    pass
                time.sleep(0.01)
        except Exception as e:
            # logger.exception(f"[FireballProxy] Pump exception: {e}")
            pass
        finally:
            pythoncom.CoUninitialize()
            try:
                if self.hwnd_proxy:
                    win32gui.DestroyWindow(self.hwnd_proxy)
            except Exception:
                pass
            self.hwnd_proxy = None
            self._running = False

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Обработчик сообщений (только ставит команды в очередь)."""
        try:
            if WM_USER <= msg < WM_USER + 1000:
                # logger.debug("Получено сообщение msg=0x%X w=%s l=%s", msg, wparam, lparam)

                # --- перехват команд ---
                if msg == WM_FIREBALL_START:
                    # logger.info("Перехвачен START")
                    self.command_queue.put("START")
                elif msg == WM_FIREBALL_STOP:
                    # logger.info("Перехвачен STOP")
                    self.command_queue.put("STOP")

                # --- пересылаем в реальное окно ---
                res = self._forward_message(msg, wparam, lparam)
                if res is None:
                    res = DEFAULT_RESPONSES.get(msg, 0)
                    # logger.debug("Ответ по умолчанию для msg=0x%X: %s", msg, res)
                else:
                    # logger.debug("Ответ от целевого окна msg=0x%X: %s", msg, res)
                    pass
                return int(res)

            if msg == win32con.WM_CLOSE:
                # logger.debug("Получено WM_CLOSE — уничтожаю окно.")
                win32gui.DestroyWindow(hwnd)
                return 0
            if msg == win32con.WM_DESTROY:
                # logger.debug("Получено WM_DESTROY — завершаю поток сообщений.")
                win32gui.PostQuitMessage(0)
                return 0

            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        except Exception as e:
            # logger.error("wndproc error: %s", e)
            return 0

    def _find_target(self, force=False) -> Optional[int]:
        """Поиск целевого окна."""
        now = time.time()
        if not force and self._target_hwnd and win32gui.IsWindow(self._target_hwnd):
            return self._target_hwnd
        if not force and (now - self._last_find_time) < self.find_interval_sec:
            return self._target_hwnd
        self._last_find_time = now

        hwnd = win32gui.FindWindow(None, self.forward_name)
        if hwnd:
            if hwnd != self._target_hwnd:
                # logger.info("Найдено целевое окно '%s' (HWND=%s)", self.forward_name, hwnd)
                pass
            self._target_hwnd = hwnd
        else:
            if self._target_hwnd:
                # logger.warning("Целевое окно '%s' потеряно.", self.forward_name)
                pass
            self._target_hwnd = None
        return self._target_hwnd

    def _forward_message(self, msg: int, wparam: int, lparam: int) -> Optional[int]:
        """Пересылает сообщение целевому окну и ждёт ответ."""
        hwnd_target = self._find_target()
        if not hwnd_target:
            # logger.warning("Целевое окно '%s' не найдено, сообщение 0x%X не доставлено.", self.forward_name, msg)
            return None

        try:
            res = win32gui.SendMessageTimeout(
                hwnd_target,
                msg,
                wparam,
                lparam,
                win32con.SMTO_ABORTIFHUNG | win32con.SMTO_NORMAL,
                self.send_timeout_ms
            )
            if isinstance(res, tuple):
                res = res[1]
            return res
        except Exception as e:
            # logger.error("Ошибка при пересылке сообщения 0x%X: %s", msg, e)
            self._target_hwnd = None
            return None
