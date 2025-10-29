import time
import queue
import serial.tools.list_ports
import src.constants as C


class DeviceModel:
    def __init__(self, controller, config, poller=None):
        """
        :param controller: SerialDeviceController
        :param config: кортеж с настройками устройства и коэфф. пересчета
        :param poller: DevicePoller (необязателен, можно запускать при подключении)
        """
        self.controller = controller
        self.poller = poller
        self.config = config
        self.command_loger = None



        # Храним статусы и последние значения
        self.status_flags = {}
        self._update_status_flags(0)
        self.settings = {
            "SET_PERIOD_M1": {"default": 17.7, "alias": "Подача уст, мм/мин"},
            "SET_PERIOD_M2": {"default": 180, "alias": "Вращение уст, об/мин"},
            "T_START": {"default": 1000, "alias": "Задержка старта, мс"},
            "T_GRIND": {"default": 1000, "alias": "Остановка в конце, мс"},
            "T_PURGING": {"default": 3000, "alias": "Время продувки, мс"},
        }
        self.settings_vars = {}
        self.last_motor_period = {
            "PERIOD_M1": 0,
            "PERIOD_M2": 0,
        }
        self.last_values = {}

        # Таймер подачи пробы
        self.start_time = 0
        self.end_time = None

        # Ускоренное движение назад инициализируется как буул вар в гуе
        self.increase_back_speed = None

        # подготовка очереди для непрерывного опроса
        if poller is not None:
            self._init_poller_queue()
            self.poller.init_func_calc_update_from_poller(self.update_from_poller)



    def _init_poller_queue(self):
        # Подготавливаем очереди для данных
        status_queue = queue.Queue(maxsize=10)
        motor1_queue = queue.Queue(maxsize=10)
        motor2_queue = queue.Queue(maxsize=10)

        self.polling_config = [
            (C.REG_STATUS, status_queue),
            (C.REG_PERIOD_M1, motor1_queue),
            (C.REG_PERIOD_M2, motor2_queue),
        ]

        self.poller.init_polling_config(self.polling_config)

    def init_command_loger(self, command_loger):
        self.command_loger = command_loger

    # Подключение

    def connect(self, port=None, baudrate=None):
        is_connect = self.controller.connect(port, baudrate)
        if is_connect:
            if self.poller is not None:
                self.poller.start()
        return is_connect

    def disconnect(self):
        if self.controller.is_connected():
            self.controller.disconnect()
        if self.poller is not None:
            if self.poller.running:
                self.poller.stop()

    def is_connected(self):
        """Проверка состояния соединения"""
        return self.controller.is_connected()

    def list_ports(self, only_with_vidpid=False):
        """Вернуть список доступных COM портов"""
        ports = []
        for p in serial.tools.list_ports.comports():
            if only_with_vidpid:
                if p.vid is None or p.pid is None:
                    continue  # пропускаем порты без VID/PID
            ports.append(p.device)
        return ports

    def find_device(self):
        """Перебрать все порты и найти подходящее устройство"""
        for port in self.list_ports(only_with_vidpid=True):
            self.controller.connect(port=port, timeout=0.02)
            if self.verify_device():
                self.port = port
                self.controller.disconnect()
                return port
            #self.controller.disconnect()
        return None

    # ------------------- Управление -------------------

    def start_process(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_CONTROL)}, write: {hex(C.CMD_START)}")
        return self._write(C.REG_CONTROL, C.CMD_START)

    def stop_process(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_CONTROL)}, write: {hex(C.CMD_NULL)}")
        return self._write(C.REG_CONTROL, C.CMD_NULL)

    def motor1_forward(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M1)}, write: {hex(C.MOTOR_CMD_START_FWD)}")
        return self._write(C.REG_COM_M1, C.MOTOR_CMD_START_FWD)

    def motor1_backward(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M1)}, write: {hex(C.MOTOR_CMD_START_BACK)}")
        return self._write(C.REG_COM_M1, C.MOTOR_CMD_START_BACK)

    def motor1_stop(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M1)}, write: {hex(C.MOTOR_CMD_STOP)}")
        return self._write(C.REG_COM_M1, C.MOTOR_CMD_STOP)

    def motor2_forward(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M2)}, write: {hex(C.MOTOR_CMD_START_FWD)}")
        return self._write(C.REG_COM_M2, C.MOTOR_CMD_START_FWD)

    def motor2_backward(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M2)}, write: {hex(C.MOTOR_CMD_START_BACK)}")
        return self._write(C.REG_COM_M2, C.MOTOR_CMD_START_BACK)

    def motor2_stop(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_M2)}, write: {hex(C.MOTOR_CMD_STOP)}")
        return self._write(C.REG_COM_M2, C.MOTOR_CMD_STOP)

    def valve1_on(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_V1)}, write: {hex(C.VALVE_CMD_ON)}")
        return self._write(C.REG_COM_V1, C.VALVE_CMD_ON)

    def valve1_off(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_V1)}, write: {hex(C.VALVE_CMD_OFF)}")
        return self._write(C.REG_COM_V1, C.VALVE_CMD_OFF)

    def valve2_on(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_V2)}, write: {hex(C.VALVE_CMD_ON)}")
        return self._write(C.REG_COM_V2, C.VALVE_CMD_ON)

    def valve2_off(self):
        if self.command_loger is not None:
            self.command_loger(f"reg: {hex(C.REG_COM_V2)}, write: {hex(C.VALVE_CMD_OFF)}")
        return self._write(C.REG_COM_V2, C.VALVE_CMD_OFF)

    def verify_device(self):
        try:
            val = self._read(C.REG_VERIFY)
            if val == C.VERIFY_CODE:
                if self.command_loger is not None:
                    self.command_loger("Устройство опознано ✅")
            else:
                if self.command_loger is not None:
                    self.command_loger(f"Ошибка: код {val}, ожидалось {hex(C.VERIFY_CODE)}")
            return val == C.VERIFY_CODE
        except Exception as e:
            if self.command_loger is not None:
                self.command_loger(f"Ошибка чтения: {e}")
            return None

    def read_period_m1(self):
        if self.command_loger is not None:
            self.command_loger(f"read reg: {hex(C.REG_PERIOD_M1)}")
        val = self._read(C.REG_PERIOD_M1)
        return val

    def read_period_m2(self):
        if self.command_loger is not None:
            self.command_loger(f"read reg: {hex(C.REG_PERIOD_M2)}")
        return self._read(C.REG_PERIOD_M2)

    def get_period_m1_us(self):
        return self.last_motor_period.get("PERIOD_M1")

    def get_period_m2_us(self):
        return self.last_motor_period.get("PERIOD_M2")

    def get_speed_m1(self):
        period = self.get_period_m1_us()
        if period and period > 0:
            return round(self.config['MOTOR_SPEED_1'] / period, 2)
        return 0

    def get_speed_m2(self):
        period = self.get_period_m2_us()
        if period and period > 0:
            return round(self.config['MOTOR_SPEED_2'] / period, 2)
        return 0

    # --------- Пересчёт в человеко-понятные величины ----------
    def period_to_speed_m1(self, period):
        if period and period > 0:
            return self.config['MOTOR_SPEED_1'] / period
        return 0

    def period_to_speed_m2(self, period):
        if period and period > 0:
            return self.config['MOTOR_SPEED_2'] / period
        return 0

    def speed_to_period_m1(self, speed):
        if speed and speed > 0:
            return int(self.config['MOTOR_SPEED_1'] / speed)
        return 0

    def speed_to_period_m2(self, speed):
        if speed and speed > 0:
            return int(self.config['MOTOR_SPEED_2'] / speed)
        return 0

    # ------------------- Настройки -------------------

    def apply_settings(self, settings_vars):
        """Принимает dict name->value из GUI, конвертирует и пишет"""
        MOTOR_SPEED_1 = self.config['MOTOR_SPEED_1']
        MOTOR_SPEED_2 = self.config['MOTOR_SPEED_2']
        self.settings_vars = settings_vars

        for name, value in settings_vars.items():
            reg = C.REGISTERS_MAP.get(name)
            if reg is None:
                continue

            if name == 'SET_PERIOD_M1' and value.get() > 0:
                value_t = int(1 / (value.get() / MOTOR_SPEED_1))
            elif name == 'SET_PERIOD_M2' and value.get() > 0:
                value_t = int(1 / (value.get() / MOTOR_SPEED_2))
            else:
                value_t = value.get()

            try:
                if self._write(reg, int(value_t)):
                    self.command_loger(f"[OK] Установлено {name} = {value_t} → регистр 0x{reg:02X}")
                else:
                    self.command_loger(f"[ERR] Ошибка при записи {name}")
            except Exception as e:
                self.command_loger(f"[ERR] Ошибка при записи {name}: {e}")

    def read_settings(self, settings_vars):
        """Читает регистры и обновляет dict name->value"""

        MOTOR_SPEED_1 = self.config['MOTOR_SPEED_1']
        MOTOR_SPEED_2 = self.config['MOTOR_SPEED_2']
        settings_vars_out = {}

        for name in settings_vars.keys():
            reg = C.REGISTERS_MAP.get(name)
            if reg is None:
                continue
            try:
                val = self._read(reg)
            except Exception as e:
                self.command_loger(f"[ERR] Ошибка при записи {name}: {e}")

            if val is None:
                self.command_loger(f"[ERR] Ошибка при чтении {name}")
                continue

            self.command_loger(f"[OK] Прочитано {name} = {val} → регистр 0x{reg:02X}")

            if name == 'SET_PERIOD_M1' and val > 0:
                val = MOTOR_SPEED_1 / val
            elif name == 'SET_PERIOD_M2' and val > 0:
                val = MOTOR_SPEED_2 / val

            settings_vars_out[name] = round(val, 2)

        return settings_vars_out

    # ------------------- Статусы и обновления -------------------

    def update_from_poller(self):
        """Разбор очередей из poller и обновление модели"""
        if self.poller is not None:
            for addr, q in self.poller.polling_config:
                while not q.empty():
                    _, val = q.get()
                    self.last_values[addr] = val

                    if addr == C.REG_STATUS:
                        self._update_status_flags(val)
                    elif addr == C.REG_PERIOD_M1:
                        self.last_motor_period["PERIOD_M1"] = val
                    elif addr == C.REG_PERIOD_M2:
                        self.last_motor_period["PERIOD_M2"] = val


    def _update_status_flags(self, value: int):
        bits = [
            "START", "BEG_BLK", "END_BLK", "M1_FWD", "M1_BACK",
            "M2_FWD", "M2_BACK", "VALVE1_ON", "VALVE2_ON", "RESET", "PING"
        ]
        for i, bit in enumerate(bits):
            self.status_flags[bit] = bool(value & (1 << i))

        # управление временем подачи
        if self.status_flags.get("BEG_BLK"):
            self.start_time = time.time()
            self.end_time = None
        if self.status_flags.get("END_BLK") and self.end_time is None:
            self.end_time = time.time()

        # Управление повышением скорости назад
        self._set_back_speed()

    #FIXME: not working
    def _set_back_speed(self):
        try:
            if self.increase_back_speed.get() and False:
                if self.status_flags.get("M1_BACK"):
                    reg_addr = C.REGISTERS_MAP.get('SET_PERIOD_M1')
                    self._write(reg_addr, int(5000))

                else:
                    reg_addr = C.REGISTERS_MAP.get('SET_PERIOD_M1')
                    MOTOR_SPEED_1 = self.config['MOTOR_SPEED_1']
                    previous_speed = self.settings_vars['SET_PERIOD_M1'].get()
                    previous_speed = 1 / (previous_speed / MOTOR_SPEED_1)
                    self._write(reg_addr, int(previous_speed))
        except AttributeError:
            pass
    def get_work_time(self):
        if self.end_time:
            return round(self.end_time - self.start_time, 1)
        if self.start_time:
            return round(time.time() - self.start_time, 1)
        return 0

    def is_end_process(self):
        return self.status_flags.get('M1_BACK')

    # ------------------- Вспомогательные -------------------

    def _write(self, reg, value):
        return self.controller.write_register(reg, value)

    def _read(self, reg):
        return self.controller.read_register(reg)
