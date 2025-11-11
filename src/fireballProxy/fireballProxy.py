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
import ctypes
from ctypes import wintypes
import xml.etree.ElementTree as ET
from src.device.device_model import DeviceModelAuger
from src.device.Desint_controller import ArduinoDesint
from src.device.device_model_flow_sensor import DeviceModelFlowSensor
import os

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

# типы WinAPI
LPVOID = ctypes.c_void_p
HANDLE = ctypes.c_void_p
DWORD = ctypes.c_uint32
LPCWSTR = ctypes.c_wchar_p

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# прототипы WinAPI функций
kernel32.OpenFileMappingW.argtypes = [DWORD, wintypes.BOOL, LPCWSTR]
kernel32.OpenFileMappingW.restype = HANDLE

kernel32.MapViewOfFile.argtypes = [HANDLE, DWORD, DWORD, DWORD, ctypes.c_size_t]
kernel32.MapViewOfFile.restype = LPVOID

kernel32.UnmapViewOfFile.argtypes = [LPVOID]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

FILE_MAP_ALL_ACCESS = 0xF001F
PAGE_READWRITE = 0x04

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
        model: Optional[DeviceModelAuger] = None,
        desint_model: Optional[ArduinoDesint] = None,
        flow_sensor_model: Optional[DeviceModelFlowSensor] = None,
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

        self.model = model
        self.desint_model = desint_model
        self.flow_sensor_model = flow_sensor_model

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
                    print(f"[FireballProxy] Pump error: {e}")
                    pass
                time.sleep(0.01)
        except Exception as e:
            # logger.exception(f"[FireballProxy] Pump exception: {e}")
            print(f"[FireballProxy] Pump exception: {e}")
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
                # --- перехват XML ---
                if msg == WM_FIREBALL_GET_XML:
                    # 1. Пересылаем команду реальному Fireball
                    res = self._forward_message(msg, wparam, lparam)

                    # 2. Читаем свежий XML из общей памяти FireBall
                    xml_text = self._read_shared_xml()

                    if xml_text:
                        # --- обновляем XML ---
                        updated_xml = self._update_xml_with_auger_data(xml_text)
                        self._write_to_shared_memory(updated_xml, "FireBall_Settigs")
                        print("[FireballProxy] XML успешно подменён в FireBall_Settigs")

                        # 4. Для отладки сохраняем копию
                        filename = os.path.join(os.getcwd(), "fireball_xml_dump.xml")
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(updated_xml)
                        print(f"[FireballProxy] XML сохранён: {filename}")

                    if res is None:
                        res = DEFAULT_RESPONSES.get(msg, 0)
                    return int(res)

                # --- перехват команд START/STOP ---
                if msg == WM_FIREBALL_START:
                    self.command_queue.put("START")
                elif msg == WM_FIREBALL_STOP:
                    self.command_queue.put("STOP")

                # --- пересылаем сообщение в реальное окно ---
                res = self._forward_message(msg, wparam, lparam)
                if res is None:
                    res = DEFAULT_RESPONSES.get(msg, 0)
                return int(res)

            if msg == win32con.WM_CLOSE:
                win32gui.DestroyWindow(hwnd)
                return 0
            if msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0

            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
        except Exception as e:
            print(f"[FireballProxy] wnd_proc error: {e}")
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
            print(f"[FireballProxy] Ошибка при пересылки сообщения: {e}")
            self._target_hwnd = None
            return None

    def _read_shared_xml(self) -> Optional[str]:
        """Прочитать XML из общей памяти 'FireBall_Settigs'."""
        FILE_MAP_READ = 0x0004
        mapping_name = "FireBall_Settigs"

        hMap = kernel32.OpenFileMappingW(FILE_MAP_READ, False, mapping_name)
        if not hMap:
            return None

        pBuf = kernel32.MapViewOfFile(hMap, FILE_MAP_READ, 0, 0, 0)
        if not pBuf:
            kernel32.CloseHandle(hMap)
            return None

        try:
            # безопасное чтение длины
            length_ptr = ctypes.cast(pBuf, ctypes.POINTER(ctypes.c_int))
            length = length_ptr.contents.value

            if length <= 0 or length > 1_000_000:
                print(f"[FireballProxy] Недопустимая длина XML: {length}")
                return None

            # читаем строку UTF-16LE начиная с offset=8
            bstr_ptr = ctypes.c_void_p(pBuf + 8)
            xml_data = ctypes.wstring_at(bstr_ptr, length)
            return xml_data

        except Exception as e:
            print(f"[FireballProxy] Ошибка при чтении XML: {e}")
            return None

        finally:
            try:
                kernel32.UnmapViewOfFile(pBuf)
            except Exception:
                pass
            try:
                kernel32.CloseHandle(hMap)
            except Exception:
                pass

    def _write_to_shared_memory(self, xml_text: str, map_name="FireBall_Settigs"):
        """Перезаписать XML в существующий FileMapping FireBall."""
        data = xml_text.encode("utf-16le")  # FireBall использует BSTR (UTF-16)
        length = len(data) // 2  # длина в wchar_t
        header = (ctypes.c_int * 2)(length, 0)  # FireBall хранит длину + резерв 4 байта

        total_size = 8 + len(data)
        hMap = kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, map_name)
        if not hMap:
            raise OSError(f"Не удалось открыть FileMapping '{map_name}'")

        pBuf = kernel32.MapViewOfFile(hMap, FILE_MAP_ALL_ACCESS, 0, 0, total_size)
        if not pBuf:
            kernel32.CloseHandle(hMap)
            raise OSError("Не удалось спроецировать память FireBall_Settigs")

        try:
            # Копируем заголовок и данные (len + 4 пустых байта + XML в UTF-16)
            ctypes.memmove(pBuf, ctypes.byref(header), 8)
            ctypes.memmove(pBuf + 8, data, len(data))
        finally:
            kernel32.UnmapViewOfFile(pBuf)
            kernel32.CloseHandle(hMap)

        print(f"[FireballProxy] XML обновлён в FireBall_Settigs ({len(data)} байт)")

    def _update_xml_with_auger_data(self, xml_text: str) -> str:
        """Добавить данные Auger в существующий XML FireBall."""

        try:
            root = ET.fromstring(xml_text)

            # Добавляем новые поля
            intr_system = ET.SubElement(root, "Auger_sample_introduction_system")

            if self.model is not None:
                s = self.model.settings_vars_str
                if len(s):
                    ET.SubElement(intr_system, "PERIOD_M1").text = s['SET_PERIOD_M1']
                    ET.SubElement(intr_system, "PERIOD_M2").text = s['SET_PERIOD_M2']
                    ET.SubElement(intr_system, "T_START").text = s['T_START']
                    ET.SubElement(intr_system, "T_GRIND").text = s['T_GRIND']
                    ET.SubElement(intr_system, "T_PURGING").text = s['T_PURGING']

            if self.desint_model is not None:
                # Дезинтегратор
                desint = ET.SubElement(root, "desint")
                ET.SubElement(desint, "frequence").text = f"{self.desint_model.frequence}"
                ET.SubElement(desint, "timeon").text = f"{self.desint_model.timeon}"

            if self.flow_sensor_model is not None:
                flow_sensor = ET.SubElement(root, "flow_sensor")
                ET.SubElement(flow_sensor, "PRESSURE").text = f"{self.flow_sensor_model.last_values_named['PRESSURE']}"
                ET.SubElement(flow_sensor, "TEMPERATURE").text = f"{self.flow_sensor_model.last_values_named['TEMPERATURE']}"
                ET.SubElement(flow_sensor, "POSITION").text = f"{self.flow_sensor_model.last_values_named['POSITION']}"

            return ET.tostring(root, encoding="utf-8").decode("utf-8")

        except Exception as e:
            print(f"[FireballProxy] Ошибка при обновлении XML: {e}")
            return xml_text
