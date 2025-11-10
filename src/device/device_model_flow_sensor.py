import time
import queue
import serial.tools.list_ports
import src.constants_flow_sensor as C
from src.device.device_controller import DeviceController
from src.device.device_poller import DevicePoller

# TODO создать класс DeviceModel для flowsensor


class DeviceModelFlowSensor:
    def __init__(self, controller: DeviceController, config=None, poller: DevicePoller | None = None):
        """
        :param controller: экземпляр TCP DeviceController
        :param config: словарь с параметрами (может быть None)
        :param poller: DevicePoller — объект фонового опроса
        """
        self.controller = controller
        self.poller = poller
        self.config = config or {}
        self.command_logger = None

        # Последние значения
        self.last_values = {}
        self.status_flags = {}
        self._update_status_flags(0)

        self.last_values_named = {
            "PRESSURE": None,
            "TEMPERATURE": None,
            "POSITION": None,
        }

        # Подготовка очередей
        if poller is not None:
            self._init_poller_queue()
            self.poller.init_func_calc_update_from_poller(self.update_from_poller)

    # ------------------- Инициализация -------------------

    def _init_poller_queue(self):
        self.status_q = queue.Queue(maxsize=10)
        self.pressure_q = queue.Queue(maxsize=10)
        self.temp_q = queue.Queue(maxsize=10)
        self.pos_lo_q = queue.Queue(maxsize=10)
        self.pos_hi_q = queue.Queue(maxsize=10)

        self.polling_config = [
            (C.REG_STATUS, self.status_q),
            (C.REG_MEASURED_PRESSURE, self.pressure_q),
            (C.REG_TEMPERATURE, self.temp_q),
            (C.REG_POSITION_LO, self.pos_lo_q),
            (C.REG_POSITION_HI, self.pos_hi_q),
        ]

        self.poller.init_polling_config(self.polling_config)

    def init_command_logger(self, logger_func):
        """Функция логирования всех команд"""
        self.command_logger = logger_func

    # ------------------- Соединение -------------------

    def connect(self):
        ok = self.controller.connect()
        if ok and self.poller is not None:
            self.poller.start()
        return ok

    def disconnect(self):
        if self.poller and self.poller.running:
            self.poller.stop()
        self.controller.disconnect()

    def is_connected(self):
        return self.controller.sock is not None

    # ------------------- Основные команды -------------------

    def start(self):
        self._log(f"START → {hex(C.CMD_START)}")
        return self._write(C.REG_COMMAND, C.CMD_START)

    def stop(self):
        self._log(f"STOP → {hex(C.CMD_STOP)}")
        return self._write(C.REG_COMMAND, C.CMD_STOP)

    def open(self):
        self._log(f"OPEN → {hex(C.CMD_OPEN)}")
        return self._write(C.REG_COMMAND, C.CMD_OPEN)

    def close(self):
        self._log(f"CLOSE → {hex(C.CMD_CLOSE)}")
        return self._write(C.REG_COMMAND, C.CMD_CLOSE)

    def save_to_flash(self):
        self._log(f"SAVE FLASH → {hex(C.CMD_SAVE_FLASH)}")
        return self._write(C.REG_COMMAND, C.CMD_SAVE_FLASH)

    def move_middle(self):
        self._log(f"MIDDLE POSITION → {hex(C.CMD_MIDDLE_POSITION)}")
        return self._write(C.REG_COMMAND, C.CMD_MIDDLE_POSITION)

    def set_position(self):
        self._log(f"SET POSITION → {hex(C.CMD_POSITION)}")
        return self._write(C.REG_COMMAND, C.CMD_POSITION)

    def sound(self):
        self._log(f"SOUND → {hex(C.CMD_SOUND)}")
        return self._write(C.REG_COMMAND, C.CMD_SOUND)

    # ------------------- Чтение и запись -------------------

    def read_pressure(self):
        return self._read(C.REG_MEASURED_PRESSURE)

    def read_temperature(self):
        return self._read(C.REG_TEMPERATURE)

    def read_position(self):
        lo = self._read(C.REG_POSITION_LO)
        hi = self._read(C.REG_POSITION_HI)
        if lo is None or hi is None:
            return None
        return (hi << 16) | lo

    def set_position_val(self, val):
        if self._write(C.REG_SET_POSITION, val):
            self._log(f"Позиция установлена: {val}")
            self._log(f"Команда отправлена: регистр 0x{C.REG_SET_POSITION:02X}, ответ 0x{val:04X}")
            return True
        else:
            self._log(f"Команда отправлена: регистр 0x{C.REG_SET_POSITION:02X}, ответа НЕТ")
            return False

    def set_pressure_val(self, val):
        """Устанавливает давление"""
        try:
            if self._write(C.REG_SET_PRESSURE, val):
                self._log(f"Команда отправлена: регистр 0x{C.REG_SET_PRESSURE:02X}, значение 0x{val:04X}")
                self._log(f"Давление установлено: {val / 10} Pa")
        except ValueError:
            self._log("Ошибка: введите число")

    # ------------------- Работа с поллером -------------------

    def update_from_poller(self):
        """Обновление данных из очередей опроса"""
        position_lo_received = False
        position_lo = 0
        for addr, q in self.poller.polling_config:
            while not q.empty():
                _, val = q.get()
                self.last_values[addr] = val

                if addr == C.REG_STATUS:
                    self._update_status_flags(val)
                elif addr == C.REG_MEASURED_PRESSURE:
                    self.last_values_named['PRESSURE'] = val / 10
                elif addr == C.REG_TEMPERATURE:
                    self.last_values_named['TEMPERATURE'] = val / 10
                elif addr == C.REG_POSITION_LO:
                    position_lo_received = True
                    position_lo = val
                elif addr == C.REG_POSITION_HI and position_lo_received:
                    # TODO работает без бита HI, если изменится, то исправить
                    position = position_lo & 0x3FFF

                    # Проверка знакового бита (бит 13, считая с 0)
                    if position & 0x2000:  # если установлен бит знака
                        position -= 0x4000  # вычитаем 2^14 для получения отрицательного значения

                    self.last_values_named['POSITION'] = position


    def _update_status_flags(self, value):
        bits = [
            'STAB', 'OPEN', 'CLOSE', 'POSITION', 'KEY STAB', 'KEY OPEN',
            'KEY CLOSE', 'ERROR', 'RESET', 'PING'
        ]
        for i, bit in enumerate(bits):
            self.status_flags[bit] = bool(value & (1 << i))

    # ------------------- Вспомогательные -------------------

    def _write(self, reg, val):
        return self.controller.write_register(reg, val)

    def _read(self, reg):
        return self.controller.read_register(reg)

    def _log(self, text):
        if self.command_logger:
            self.command_logger(text)
        else:
            print(text)
