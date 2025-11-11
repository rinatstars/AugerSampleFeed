"""Модуль для управления устройством через Modbus"""

import socket
import threading
import time
from typing import Optional
from src.constants_flow_sensor import (
    DEFAULT_PORT, DEFAULT_DEVICE_ID, RECONNECT_ATTEMPTS, RECONNECT_DELAY,
    READ_TIMEOUT, WRITE_TIMEOUT
)
from src.crc import crc7_generate


class DeviceController:
    """Класс для управления устройством через TCP-соединение"""

    def __init__(self, ip, port=DEFAULT_PORT, device_id=DEFAULT_DEVICE_ID):
        """Инициализация контроллера устройства"""
        self.ip = ip
        self.port = port
        self.device_id = device_id & 0x07  # 3 бита (0-7)
        self.sock: Optional[socket.socket] = None
        self.connection_lock = threading.Lock()
        self.running = False
        self.reconnect_attempts = RECONNECT_ATTEMPTS
        self.reconnect_delay = RECONNECT_DELAY
        self.read_timeout = READ_TIMEOUT
        self.write_timeout = WRITE_TIMEOUT
        self.t = threading.Thread()
        self.start_polling_time = time.time()
        self.func_calc_time = None

    def _reconnect(self):
        """Пытается переподключиться к устройству"""
        with self.connection_lock:
            for attempt in range(self.reconnect_attempts):
                try:
                    self._close_socket()
                    self.sock = self._create_socket()
                    print("Успешное подключение сокета TCP")
                    return True
                except Exception as e:
                    print(f"Попытка подключения сокета {attempt + 1}/{self.reconnect_attempts}: {e}")
                    time.sleep(self.reconnect_delay)
            return False

    def _create_socket(self):
        """Создает и настраивает сокет"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.read_timeout)
        sock.connect((self.ip, self.port))
        return sock

    def _close_socket(self):
        """Закрывает сокет, если он открыт"""
        if self.sock:
            self.sock.close()
            self.sock = None

    def _ensure_connection(self):
        """Проверяет и восстанавливает соединение при необходимости"""
        if self.sock is None:
            return self._reconnect()

        try:
            self.sock.settimeout(1)
            self.sock.sendall(b'')  # Тестовый пустой пакет
            return True
        except (socket.timeout, socket.error, ConnectionError) as e:
            print(f"Ошибка связи сокета: {e}")
            return self._reconnect()

    def connect(self):
        """Устанавливает первоначальное соединение"""
        return self._reconnect()

    def _build_frame(self, address, write=False, data=0x0000):
        """Собирает кадр согласно протоколу."""
        byte1 = (
                0xC0 |
                (0x20 if write else 0x00) |
                ((data >> 15) & 0x01) << 4 |
                ((data >> 14) & 0x01) << 3 |
                self.device_id
        )
        byte2 = address & 0x7F
        byte3 = (data >> 7) & 0x7F
        byte4 = data & 0x7F

        frame = bytes([byte1, byte2, byte3, byte4])
        crc = crc7_generate(frame)
        return frame + bytes([crc & 0x7F])

    def _parse_response(self, response, expected_address):
        """Парсит ответное сообщение."""
        if len(response) != 5:
            return None
        if (response[0] & 0xC0) != 0xC0:
            return None
        if (response[0] & 0x07) != self.device_id:
            return None
        if (response[1] & 0x7F) != expected_address:
            return None
        if crc7_generate(response[:4]) != (response[4] & 0x7F):
            return None

        return (
                ((response[0] >> 4) & 0x03) << 14 |
                (response[2] & 0x7F) << 7 |
                response[3] & 0x7F
        )

    def read_register(self, address):
        """Чтение регистра с автоматическим переподключением"""
        for attempt in range(3):
            try:
                if not self._ensure_connection() or self.sock is None:
                    continue

                request = self._build_frame(address, write=False)
                self.sock.settimeout(self.read_timeout)
                self.sock.sendall(request)
                response = self.sock.recv(5)

                if not response:
                    raise socket.error("Пустой ответ от устройства")

                return self._parse_response(response, address)

            except (socket.timeout, socket.error, ConnectionError) as e:
                print(f"Ошибка связи сокета (попытка {attempt + 1}): {e}")
                self.sock = None
                if not self._reconnect():
                    continue
            except Exception as e:
                print(f"Ошибка чтения регистра 0x{address:02X}: {e}")
                break

        return None

    def write_register(self, address, value):
        """Запись регистра с автоматическим переподключением"""
        for attempt in range(3):
            try:
                if not self._ensure_connection() or self.sock is None:
                    continue

                request = self._build_frame(address, write=True, data=value)
                self.sock.settimeout(self.write_timeout)
                self.sock.sendall(request)
                response = self.sock.recv(5)

                if not response:
                    raise socket.error("Пустой ответ")

                return self._parse_response(response, address) is not None

            except (socket.timeout, socket.error, ConnectionError) as e:
                print(f"Ошибка связи сокета (попытка {attempt + 1}): {e}")
                self.sock = None
                if not self._reconnect():
                    continue
            except Exception as e:
                print(f"Ошибка записи регистра 0x{address:02X}: {e}")
                break

        return False

    def init_func_time_culc(self, func):
        self.func_calc_time = func

    def disconnect(self):
        """Закрывает соединение"""
        with self.connection_lock:
            self._close_socket()
