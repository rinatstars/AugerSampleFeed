import time
import queue
import serial.tools.list_ports
import src.constants as C
from src.device.serial_device_controller import SerialDeviceController


class DeviceModelAuger:
    def __init__(self, controller: SerialDeviceController, config, poller=None, desint=None, sensor=None):
        """
        :param controller: SerialDeviceController
        :param config: кортеж с настройками устройства и коэфф. пересчета
        :param poller: DevicePoller (необязателен, можно запускать при подключении)
        """
        self.controller = controller
        self.poller = poller
        self.config = config
        self.desint = desint
        self.sensor = sensor
        self.on_desint = False
        self.command_loger = None

        self.manual = None
        self.manual_start = False
        self.manual_start_time = time.time()

        self.puring_end = False
        self.puring_time_counter = [time.time(), 0, False]
        self.purge_count = 3


        # Храним статусы и последние значения
        self.status_flags = {}
        self._update_status_flags(0)
        self.settings = {
            "SET_PERIOD_M1": {"default": 8, "alias": "Подача уст, мг/с"},
            "SET_PERIOD_M2": {"default": 180, "alias": "Вращение уст, об/мин"},
            "T_START": {"default": 1000, "alias": "Задержка старта, мс"},
            "T_GRIND": {"default": 1000, "alias": "Остановка в конце, мс"},
            "T_PURGING": {"default": 3000, "alias": "Время продувки, мс"},
        }
        self.settings_vars = {}
        self.settings_vars_str = {}
        self.last_motor_period = {
            "PERIOD_M1": 0,
            "PERIOD_M2": 0,
        }
        self.last_values = {}

        # Таймер подачи пробы
        self.start_time = time.time()
        self.end_time = 0

        self.delta_time = time.time()
        self.position = 0

        # Ускоренное движение назад инициализируется как буул вар в гуе
        self.increase_back_speed = None
        self.m1_back = False

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

    def start_process_manual_init(self, on_desint=False):
        self.manual_start = True
        self.manual_start_time = time.time()
        self.on_desint = on_desint
        self.command_loger(f'Старт инициализирован', 'success')

    def start_process_manual(self):
        self.manual_start = False
        self.motor1_forward()
        self.motor2_forward()
        if self.on_desint and self.desint is not None:
            self.desint.send_start()

    def stop_process_manual(self):
        if self.manual_start:
            self.manual_start = False
            self.command_loger(f'Старт отменён', 'warning')

        if not self.is_end_process():
            self.motor1_stop()
            self.motor2_stop()

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

    def valve1_switch(self):
        if self.status_flags.get('VALVE1_ON'):
            self.valve1_off()
        elif not self.status_flags.get('VALVE2_ON'):
            self.valve1_on()

    def valve2_switch(self):
        if self.status_flags.get('VALVE2_ON'):
            self.valve2_off()
        elif not self.status_flags.get('VALVE2_ON'):
            self.valve2_on()

    def verify_device(self):
        try:
            val = self._read(C.REG_VERIFY)
            # Проверяем, что первые 4 бита (1 hex цифра) равны 0x5
            # и следующие 4 бита (следующая hex цифра) равны 0x6
            if (val >> 8) & 0xFF == 0x56:
                if self.command_loger is not None:
                    # Извлекаем версию из младших битов (предполагая, что версия в последних 8 битах)
                    version = val & 0xFF
                    self.command_loger(f"Устройство опознано ✅ Версия: 0.{version}")
                return True
            else:
                if self.command_loger is not None:
                    self.command_loger(f"Ошибка: код {hex(val)}, ожидалось начало 0x56XX")
                return False
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
        self.settings_vars = settings_vars.copy()

        for name, value in settings_vars.items():
            self.settings_vars_str[name] = str(value.get())
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

    def go_back(self):
        self.motor2_forward()
        self.motor1_backward()
        if self.puring_end:
            self.puring_init()

    def puring_init(self):
        self.puring_time_counter = [time.time(), 0, True]
        if self.sensor is not None:
            self.sensor.open()

    def _update_status_flags(self, value: int):
        bits = [
            "START", "BEG_BLK", "END_BLK", "M1_FWD", "M1_BACK",
            "M2_FWD", "M2_BACK", "VALVE1_ON", "VALVE2_ON", "RESET", "PING"
        ]
        for i, bit in enumerate(bits):
            self.status_flags[bit] = bool(value & (1 << i))

        # управление временем подачи
        self.find_property_auger()

        # Управление повышением скорости назад
        self._set_back_speed()

        # Управление возвратом назад по достижению концевика
        self._go_back_controll()

        # Управление отложенным стартом
        self._manual_start_controll()

        # Управление множественными продувками
        self._puring_control()

        # Отключение дезинтегратора по пути назад
        self.off_desint_back()

    def off_desint_back(self):
        if self.desint and self.desint.is_connected() and self.desint.is_running:
            if self.is_end_process():
                self.desint.send_end()

    def _manual_start_controll(self):
        if self.manual_start:
            delay_time = (time.time() - self.manual_start_time) * 1000
            start_time = self.settings_vars.get('T_START')
            if start_time is None:
                self.apply_settings(self.read_settings(self.settings))
                start_time = self.settings_vars.get('T_START')

            start_time = start_time.get()

            if delay_time >= start_time:
                self.manual_start = False
                self.start_process_manual()

    def _go_back_controll(self):
        if self.manual and self.is_end_blk() and not self.is_end_process():
            self.go_back()

        if self.is_beg_blk() and self.is_m2_run() and not self.is_m1_run():
            self.motor2_stop()

    def _puring_control(self):
        if self.puring_time_counter[2]:
            if (time.time() - self.puring_time_counter[0]) * 1000 > self.settings_vars.get('T_PURGING').get():
                self.valve2_switch()
                self.puring_time_counter[0] = time.time()
                self.puring_time_counter[1] += 1
            if self.puring_time_counter[1] >= self.purge_count * 2:
                self.puring_time_counter = [time.time(), 0, False]
                self.valve2_off()
                if self.sensor is not None:
                    self.sensor.start()

    def find_property_auger(self):
        if self.status_flags.get("BEG_BLK") and not self.is_m1_run():
            self.start_time = time.time()
            self.position = 0
            self.end_time = 0

        if self.status_flags.get("M1_FWD"):
            speed = self.period_to_speed_m1(self.last_motor_period["PERIOD_M1"])
            self.position += speed * (time.time() - self.delta_time)
            self.end_time += time.time() - self.delta_time
        if self.status_flags.get("M1_BACK"):
            speed = self.period_to_speed_m1(self.last_motor_period["PERIOD_M1"])
            self.position -= speed * (time.time() - self.delta_time)
        self.delta_time = time.time()

    def _set_back_speed(self):
        try:
            if self.increase_back_speed:
                if self.status_flags.get("M1_BACK") and not self.m1_back:
                    reg_addr = C.REGISTERS_MAP.get('SET_PERIOD_M1')
                    self._write(reg_addr, int(5000))
                    self.m1_back = True
                elif self.m1_back and self.is_beg_blk():
                    self.apply_settings(self.settings_vars)
                    self.m1_back = False
        except AttributeError:
            pass

    def get_work_time(self):
        # if self.end_time:
        #     return round(self.end_time - self.start_time, 1)
        # if self.start_time:
        #     return round(time.time() - self.start_time, 1)
        # return 0
        return self.end_time

    def is_end_process(self):
        return self.status_flags.get('M1_BACK')

    def is_end_blk(self):
        return self.status_flags.get('END_BLK')

    def is_beg_blk(self):
        return self.status_flags.get('BEG_BLK')

    def is_m2_run(self):
        return self.status_flags.get('M2_FWD') or self.status_flags.get('M2_BACK')

    def is_m1_run(self):
        return self.status_flags.get('M1_FWD') or self.status_flags.get('M1_BACK')

    # ------------------- Вспомогательные -------------------

    def _write(self, reg, value):
        return self.controller.write_register(reg, value)

    def _read(self, reg):
        return self.controller.read_register(reg)
