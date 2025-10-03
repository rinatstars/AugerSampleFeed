import serial
import threading
import time
from src import constants as C
from src.crc import crc7_generate


class SerialDeviceController:
    """Класс для работы с устройством по RS232 (VMK Protocol, CRC7)"""

    def __init__(self, port=C.DEFAULT_PORT, baudrate=C.DEFAULT_BAUDRATE,
                 device_id=C.DEFAULT_DEVICE_ID, timeout=C.READ_TIMEOUT):
        self.port = port
        self.baudrate = baudrate
        self.device_id = device_id
        self.timeout = timeout
        self.lock = threading.Lock()
        self.serial = None

    @property
    def serial_port(self):
        """Совместимость с GUI"""
        return self.serial

    def connect(self, port=None, baudrate=None, timeout=None):
        """Открывает COM-порт и запускает опрос"""
        if port:
            self.port = port
        if baudrate:
            self.baudrate = baudrate
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=timeout if timeout is not None else self.timeout,
                write_timeout=timeout if timeout is not None else C.WRITE_TIMEOUT
            )
            if self.serial.is_open:
                #self.start_polling()
                return True
            return False
        except Exception as e:
            print(f"[ERROR] Не удалось открыть {self.port}: {e}")
            self.serial = None
            return False

    def disconnect(self):
        """Закрывает порт и останавливает опрос"""
        #self.stop_polling()
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

    def is_connected(self):
        """Проверка состояния соединения"""
        return self.serial is not None and self.serial.is_open

    # ------------------- VMK Protocol -------------------

    def _build_frame(self, address, write=False, data=0x0000):
        """Собирает кадр согласно VMK протоколу"""
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
        """Парсит ответ от устройства"""
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
                ((response[0] >> 3) & 0x03) << 14 |
                (response[2] & 0x7F) << 7 |
                response[3] & 0x7F
        )

    # ------------------- API -------------------

    def read_register(self, address):
        """Чтение регистра"""
        with self.lock:
            if not self.is_connected():
                return None
            try:
                request = self._build_frame(address, write=False)
                self.serial.reset_input_buffer()
                self.serial.write(request)
                #time.sleep(0.02)
                response = self.serial.read(5)
                return self._parse_response(response, address)
            except Exception as e:
                print(f"[ERROR] read_register 0x{address:02X}: {e}")
                return None

    def write_register(self, address, value):
        """Запись в регистр"""
        with self.lock:
            if not self.is_connected():
                return False
            try:
                request = self._build_frame(address, write=True, data=value)
                self.serial.reset_input_buffer()
                self.serial.write(request)
                time.sleep(0.005)
                response = self.serial.read(5)
                return self._parse_response(response, address) is not None
            except Exception as e:
                print(f"[ERROR] write_register 0x{address:02X}: {e}")
                return False