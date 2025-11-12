import tkinter as tk
import time
import sys
from pathlib import Path
from tkinter import ttk, scrolledtext, messagebox, StringVar, BooleanVar, IntVar
from src.device.device_model import DeviceModelAuger
from src.device.device_model_flow_sensor import DeviceModelFlowSensor


def resource_path(relative: str) -> str:
    """Возвращает абсолютный путь к ресурсу (иконке, файлу и т.п.)"""
    base_path = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent.parent)
    base_path = Path(base_path)  # гарантируем Path
    return str(base_path / relative)


class DeviceGUI:
    def __init__(self, model_auger, desint_model=None, model_flow_sensor=None):
        """
        :param model_auger: экземпляр DeviceModel
        :param desint_model: экземпляр ArduinoDesint
        :param model_flow_sensor: экземпляр DeviceModelFlowSensor
        """
        self.model_auger: DeviceModelAuger = model_auger
        self.desint_model = desint_model
        self.model_flow_sensor: DeviceModelFlowSensor = model_flow_sensor
        self.model_auger.init_command_loger(self.append_command_log)
        self.model_flow_sensor.init_command_logger(self.append_command_log)
        self.comand_loger_queue = []

        self.window = tk.Tk()
        self.window.title("Auger sample introduction system")
        self.window.geometry("1500x950")
        icon_path = resource_path("icon.ico")
        self.window.iconbitmap(icon_path)

        self.interval_polling = StringVar(value="Обновление окна: ---мс")
        self.interval_upd_data = StringVar(value="Обновление данных: ---мс")
        self.interval_work_auger = StringVar(value="Время подачи пробы: ---с")
        self.position_work_auger = StringVar(value="Осталось пробы: ---мг")

        self.text_press = "Давление"

        self._setup_ui()
        self._start_background_tasks()

        if self.model_auger.poller is not None:
            self.model_auger.poller.init_func_time_calc(self._update_interval_upd_data)

        self.start_time = 0
        self.end_time = None

    # ---------------- UI ----------------
    def _setup_ui(self):
        main_container = ttk.Frame(self.window, padding="10")
        main_container.pack(fill="both", expand=True)
        main_container.columnconfigure(0, weight=0)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(main_container)
        left_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        middle_frame = ttk.Frame(main_container)
        middle_frame.grid(row=0, column=1, sticky="nsw")

        right_frame = ttk.Frame(main_container)
        right_frame.grid(row=0, column=2, sticky="nsw", padx=(10, 0))

        # Пробоподача
        self._create_connection_frame(left_frame)
        self._create_status_frame(left_frame)
        self._create_settings_frame(left_frame)
        self._create_control_frame(left_frame)
        self._create_verify_frame(left_frame)
        # Дезинтегратор
        self._create_connection_desint_frame(middle_frame)
        self._create_desint_frame(middle_frame)
        self._create_ping_frame(left_frame)
        self._create_time_work_frame(left_frame)
        # Вытяжка
        self._create_status_frame_flow_sensor(middle_frame)
        self._create_temperature_frame(middle_frame)
        self._create_position_frame(middle_frame)
        self._create_pressure_frame(middle_frame)
        self._create_command_frame(middle_frame)
        # self._create_log_frame(left_frame)
        # Лог
        self._create_log_frame(right_frame)
        self._setup_keyboard_bindings()

        # Обновляем окно для расчета размеров
        self.window.update_idletasks()

        # Получаем требуемую ширину и высоту содержимого
        req_width = main_container.winfo_reqwidth() + 20  # + padding
        req_height = main_container.winfo_reqheight() + 20  # + padding

        # Устанавливаем минимальный размер окна
        self.window.minsize(req_width, req_height)

        # Устанавливаем текущий размер окна под содержимое
        self.window.geometry(f"{req_width}x{req_height}")

    def _setup_keyboard_bindings(self):
        """Настройка обработчиков клавиатуры"""
        # Привязываем обработчики ко всему окну
        self.window.bind('<KeyPress>', self._on_key_press)
        # self.window.bind('<KeyRelease>', self._on_key_release)

        # Фокусируем окно, чтобы оно получало события клавиатуры
        self.window.focus_set()

    def _on_key_press(self, event):
        """Обработка нажатия клавиш"""
        key = event.keysym.lower()

        if key == 'space' and self.model_auger.is_connected():
            self.model_auger.start_process()
            self.append_command_log('Запуск по пробелу')

    def _create_connection_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Подключение", padding=5)
        frame.pack(fill="x", pady=5)

        ports = self.model_auger.list_ports()
        if not ports:
            ports = ["Нет портов"]

        ttk.Label(frame, text="Порт:").grid(row=0, column=0, sticky="w")

        self.port_var = tk.StringVar(value=ports[0])
        self.port_combo = ttk.Combobox(
            frame, textvariable=self.port_var, values=ports, width=12, state="readonly"
        )
        self.port_combo.grid(row=0, column=1, padx=2, pady=2)

        refresh_btn = ttk.Button(frame, text="⟳", width=3, command=self._refresh_ports)
        refresh_btn.grid(row=0, column=2, padx=2, sticky="w")

        ttk.Label(frame, text="Baudrate:").grid(row=0, column=3, sticky="w")
        self.baud_var = tk.IntVar(value=self.model_auger.config.get("baudrate", 38400))
        ttk.Entry(frame, textvariable=self.baud_var, width=8).grid(row=0, column=4, padx=2)

        self.connect_btn = ttk.Button(frame, text="Подключить", command=self._toggle_connection)
        self.connect_btn.grid(row=1, column=0, columnspan=2, padx=5)

        # Кнопка найти устройство
        find_btn = ttk.Button(frame, text="Найти устройство", command=self._find_device)
        find_btn.grid(row=1, column=2, columnspan=3, padx=5)

    def _create_connection_desint_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Подключение дезинтегратора", padding=5)
        frame.pack(fill="x", pady=5)

        ports = self.model_auger.list_ports()
        if not ports:
            ports = ["Нет портов"]

        ttk.Label(frame, text="Порт:").grid(row=0, column=0, sticky="w")

        self.port_var_desint = tk.StringVar(value=ports[0])
        self.port_combo_desint = ttk.Combobox(
            frame, textvariable=self.port_var_desint, values=ports, width=12, state="readonly"
        )
        self.port_combo_desint.grid(row=0, column=1, padx=2, pady=2)

        refresh_btn = ttk.Button(frame, text="⟳", width=3, command=self._refresh_ports)
        refresh_btn.grid(row=0, column=2, padx=2, sticky="w")

        ttk.Label(frame, text="Baudrate:").grid(row=0, column=3, sticky="w")
        self.baud_var_desint = tk.IntVar(value=9600)
        ttk.Entry(frame, textvariable=self.baud_var_desint, width=8).grid(row=0, column=4, padx=2)

        self.connect_btn_desint = ttk.Button(frame, text="Подключить", command=self._toggle_connection_desint)
        self.connect_btn_desint.grid(row=1, column=0, columnspan=2, padx=5)

        # Кнопка найти устройство
        find_btn = ttk.Button(frame, text="Найти устройство", command=self._find_device)
        find_btn.grid(row=1, column=2, columnspan=3, padx=5)

    def _create_status_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Статус", padding=5)
        frame.pack(fill="x", pady=5)

        self.status_vars = {}
        for i, bit in enumerate(self.model_auger.status_flags):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(frame, text=bit, variable=var, state="disabled")
            cb.grid(row=i // 4, column=i % 4, sticky="w")
            self.status_vars[bit] = var

        ttk.Label(frame, text="Подача, мг/с").grid(row=3, column=0, sticky="w")
        self.inning_speed = tk.DoubleVar(value=0)
        entry_period_m1 = ttk.Label(frame, textvariable=self.inning_speed, width=10)
        entry_period_m1.grid(row=3, column=1, sticky="w")

        ttk.Label(frame, text="Вращение, об/мин").grid(row=3, column=2, sticky="w")
        self.rotate_speed = tk.DoubleVar(value=0)
        entry_period_m2 = ttk.Label(frame, textvariable=self.rotate_speed, width=10)
        entry_period_m2.grid(row=3, column=3, sticky="w")

    def _create_settings_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Настройки", padding=5)
        frame.pack(fill="x", pady=5)

        self.setting_vars = {}
        self.setting_vars_raw = {}
        self._syncing = False

        for i, (name, meta) in enumerate(self.model_auger.settings.items()):
            # Человеческое поле
            ttk.Label(frame, text=meta["alias"]).grid(row=i, column=0, sticky="w")
            var_human = tk.DoubleVar(value=meta["default"])
            spin_human = ttk.Spinbox(frame, from_=0, to=100000, increment=1,
                                     textvariable=var_human, width=10)
            spin_human.grid(row=i, column=1, sticky="w")
            self.setting_vars[name] = var_human

            # Сырое поле (период)
            if i < 2:
                ttk.Label(frame, text="период, мс").grid(row=i, column=2, sticky="w")
                if "M1" in name:
                    init_val = self.model_auger.speed_to_period_m1(meta["default"])
                else:
                    init_val = self.model_auger.speed_to_period_m2(meta["default"])
                var_raw = tk.IntVar(value=init_val)
                spin_raw = ttk.Spinbox(frame, from_=0, to=100000, increment=100,
                                       textvariable=var_raw, width=10)
                spin_raw.grid(row=i, column=3, sticky="w")
                self.setting_vars_raw[name] = var_raw

            # Связь двух полей
            var_human.trace_add("write", lambda *_,
                                                n=name: self._update_raw_from_human(n))
            var_raw.trace_add("write", lambda *_,
                                              n=name: self._update_human_from_raw(n))


        ttk.Button(frame, text="Применить", command=self._apply_settings).grid(
            row=len(self.setting_vars), column=0, columnspan=2, pady=5
        )
        ttk.Button(frame, text="Прочитать", command=self._read_settings).grid(
            row=len(self.setting_vars), column=2, columnspan=2, pady=5
        )

    def _update_raw_from_human(self, name):
        if name in self.setting_vars_raw:
            if self._syncing:
                return
            self._syncing = True
            try:
                try:
                    val = self.setting_vars[name].get()
                except tk.TclError:
                    val = 0
                if "M1" in name:
                    self.setting_vars_raw[name].set(self.model_auger.speed_to_period_m1(val))
                else:
                    self.setting_vars_raw[name].set(self.model_auger.speed_to_period_m2(val))
            finally:
                self._syncing = False

    def _update_human_from_raw(self, name):
        if name in self.setting_vars_raw:
            if self._syncing:
                return
            self._syncing = True
            try:
                try:
                    val = self.setting_vars_raw[name].get()
                except tk.TclError:
                    val = 0
                if "M1" in name:
                    self.setting_vars[name].set(round(self.model_auger.period_to_speed_m1(val), 2))
                else:
                    self.setting_vars[name].set(round(self.model_auger.period_to_speed_m2(val), 2))
            finally:
                self._syncing = False

    def _create_control_frame(self, parent):
        style = ttk.Style()
        style.configure("Start.TButton", background="green")
        style.configure("Stop.TButton", background="red")

        frame = ttk.LabelFrame(parent, text="Управление", padding=5)
        frame.pack(fill="x", pady=5)

        ttk.Button(frame, text="СТАРТ", command=self.start_process).grid(row=0, column=0, padx=5)

        ttk.Button(frame, text="СТАРТ Ручн.", command=self.start_process_manual).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="СТОП", command=self.stop_process_manual).grid(row=0, column=2, padx=5)
        ttk.Button(frame, text="НАЗАД", command=self.model_auger.go_back).grid(row=0, column=3, padx=5)

        ttk.Label(frame, text="Мотор 1:").grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=self.model_auger.motor1_forward).grid(row=1, column=1)
        ttk.Button(frame, text="Назад", command=self.model_auger.motor1_backward).grid(row=1, column=2)
        ttk.Button(frame, text="Стоп", command=self.model_auger.motor1_stop).grid(row=1, column=3)

        ttk.Label(frame, text="Мотор 2:").grid(row=2, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=self.model_auger.motor2_forward).grid(row=2, column=1)
        ttk.Button(frame, text="Назад", command=self.model_auger.motor2_backward).grid(row=2, column=2)
        ttk.Button(frame, text="Стоп", command=self.model_auger.motor2_stop).grid(row=2, column=3)

        ttk.Label(frame, text="Клапана:").grid(row=3, column=0, sticky="w")



        self.switch_v1 = ttk.Button(frame, text="Клапан 1", command=self.model_auger.valve1_switch,
                                    style="Stop.TButton")
        self.switch_v1.grid(row=3, column=1)
        self.switch_v2 = ttk.Button(frame, text="Клапан 2", command=self.model_auger.valve2_switch,
                                    style="Stop.TButton")
        self.switch_v2.grid(row=3, column=2)

        ttk.Label(frame, text="Продувка:").grid(row=4, column=0, sticky="w")
        ttk.Button(frame, text="Продуть", command=self.model_auger.puring_init).grid(row=4, column=1)
        ttk.Label(frame, text="Количество:").grid(row=4, column=2, sticky="w", padx=(10, 0))
        self.purge_count = IntVar(value=3)
        purge_spinbox = ttk.Spinbox(frame, from_=1, to=100, textvariable=self.purge_count, width=5)
        purge_spinbox.grid(row=4, column=3, sticky="w", padx=5)

        self.increase_back_speed = BooleanVar(value=True)
        self.manual = BooleanVar(value=True)
        self.puring_end = BooleanVar(value=True)
        ttk.Label(frame, text="Настройка:").grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(frame, text='Ускорить назад', variable=self.increase_back_speed).grid(row=6, column=1)
        ttk.Checkbutton(frame, text='Ручной старт', variable=self.manual).grid(row=6, column=2)
        ttk.Checkbutton(frame, text='Продувка', variable=self.puring_end).grid(row=6, column=3)

    def start_process(self):
        if self.manual.get():
            self.start_process_manual()
            return
        self.model_auger.start_process()
        if self.on_desint.get():
            self.desint_model.send_start()

    def stop_process(self):
        if self.manual.get():
            self.stop_process_manual()
            return
        self.model_auger.stop_process()
        if self.on_desint.get():
            self.desint_model.send_end()

    def start_process_manual(self):
        self.model_auger.start_process_manual_init(self.on_desint.get())

    def stop_process_manual(self):
        self.model_auger.stop_process_manual()

        if self.on_desint.get():
            self.desint_model.send_end()

    def _create_desint_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Дезинтегратор", padding=5)
        frame.pack(fill="x", pady=5)

        ttk.Label(frame, text='Импульс:').grid(row=0, column=0, sticky="w")
        self.var_impulse = tk.DoubleVar(value=5)
        spin_impulse = ttk.Spinbox(frame, from_=0, to=60, increment=1,
                                   textvariable=self.var_impulse, width=10)
        spin_impulse.grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text='Частота:').grid(row=0, column=2, sticky="w")
        self.var_frequence = tk.DoubleVar(value=15)
        spin_frequence = ttk.Spinbox(frame, from_=0, to=60, increment=1,
                                    textvariable=self.var_frequence, width=10)
        spin_frequence.grid(row=0, column=3, sticky="w")

        ttk.Label(frame, text="Управление:").grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Старт", command=self.desint_model.send_start).grid(row=1, column=1)
        ttk.Button(frame, text="Стоп", command=self.desint_model.send_end).grid(row=1, column=2)
        ttk.Button(frame, text="Применить", command=self.apply_desint_settings).grid(row=1, column=3)
        self.on_desint = BooleanVar(value=False)

        ttk.Checkbutton(frame, text='Включать', variable=self.on_desint).grid(row=1, column=4)

    def apply_desint_settings(self):
        self.desint_model.set_pwm(self.var_impulse.get(), self.var_frequence.get())

    def _create_verify_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Верификация", padding=5)
        frame.pack(fill="x", pady=5)
        ttk.Button(frame, text="Проверить устройство", command=self.model_auger.verify_device).pack()

    def _create_ping_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Связь", padding="5")
        frame.pack(fill='x', pady=5)
        ttk.Label(frame, textvariable=self.interval_polling).grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(frame, textvariable=self.interval_upd_data).grid(row=0, column=1, padx=5, sticky='w')

    def _create_time_work_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Время работы", padding="5")
        frame.pack(fill='x', pady=5)
        ttk.Label(frame, textvariable=self.interval_work_auger).grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(frame, textvariable=self.position_work_auger).grid(row=0, column=1, padx=5, sticky='w')
        # Отдельный фрейм для прогресс-бара
        frame_progress = ttk.Frame(parent)
        frame_progress.pack(fill='x', pady=5)

        self.progress = ttk.Progressbar(frame_progress, mode='determinate')
        self.progress.pack(fill='x', padx=5)

    def _create_status_frame_flow_sensor(self, parent):
        """Создает фрейм статуса"""
        frame = ttk.LabelFrame(parent, text="Статус", padding="5")
        frame.pack(fill='x', pady=5)

        self.status_vars_flow_sensor = {}
        for i, bit in enumerate(self.model_flow_sensor.status_flags):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(frame, text=bit, variable=var, state="disabled")
            cb.grid(row=i // 4, column=i % 4, sticky="w")
            self.status_vars_flow_sensor[bit] = var

    def _create_temperature_frame(self, parent):
        """Создает фрейм температуры"""
        frame = ttk.LabelFrame(parent, text="Температура", padding="5")
        frame.pack(fill='x', pady=5)

        self.temperature_var = StringVar(value="--- °C")

        ttk.Label(frame, textvariable=self.temperature_var, font=('Arial', 12)).pack()

    def _create_position_frame(self, parent):
        """Создает фрейм позиции"""
        frame = ttk.LabelFrame(parent, text="Позиция заслонки", padding="5")
        frame.pack(fill='x', pady=5)

        self.position_var = IntVar(value=0)
        self.position_var_set = IntVar(value=0)
        self.position_text_var = StringVar(value="Позиция изм.: ---")
        self.position_text_var_set = StringVar(value="Позиция уст.: ---")

        ttk.Label(frame, textvariable=self.position_text_var).grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(frame, textvariable=self.position_text_var_set).grid(row=0, column=1, padx=5, sticky='w')
        ttk.Scale(frame, variable=self.position_var_set, from_=0, to=4096, length=300, command=self._set_position_var).grid( # 4294967295
            row=1, column=0, columnspan=2, padx=5, sticky='w'
        )
        ttk.Button(frame, text="Применить", command=self._set_position).grid(
            row=2, column=0, columnspan=2, padx=5, sticky='n'
        )

    def _set_position_var(self, value):
        """Меняет значение переменной с текстом установленного положения заслонки"""
        value = self.position_var_set.get()
        self.position_text_var_set.set(f"Позиция уст.: {value}")

    def _set_position(self):
        """Устанавливает позицию заслонки"""
        value = self.position_var_set.get()
        if self.model_flow_sensor.set_position_val(value):
            self.append_command_log(f"Позиция установлена: {value}")
        else:
            self.append_command_log(f"Ошибка установки позиции, ответа НЕТ")

    def _change_speed_press(self):
        if self.calc_speed:
            self.text_press = "Скорость"
        else:
            self.text_press = "Давление"

    def _create_pressure_frame(self, parent):
        """Создает фрейм давления"""
        frame = ttk.LabelFrame(parent, text=self.text_press, padding="5")
        frame.pack(fill='x', pady=5)

        self.calc_speed = False

        self.measured_pressure_var = StringVar(value="--- Pa")
        self.set_pressure_var = StringVar(value="0")

        ttk.Label(frame, text="Измеренное:").grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(frame, textvariable=self.measured_pressure_var).grid(row=0, column=1, padx=5, sticky='w')

        ttk.Label(frame, text="Уставка:").grid(row=1, column=0, padx=5, sticky='w')
        self.pressure_spinbox = ttk.Spinbox(
            frame, from_=0, to=10000, textvariable=self.set_pressure_var, width=10
        )
        self.pressure_spinbox.grid(row=1, column=1, padx=5)
        ttk.Button(frame, text="Прочитать", command=self._read_set_pressure).grid(row=1,
                                                                                                 column=2, padx=5)
        ttk.Button(frame, text="Применить", command=self._set_pressure).grid(row=1, column=3, padx=5)

        cb = ttk.Checkbutton(frame, text="Скорость", variable=self.calc_speed, command=self._change_speed_press)
        cb.grid(row=2, column=0, padx=5, sticky='w')

    def _create_command_frame(self, parent):
        """Создает фрейм команд"""
        frame = ttk.LabelFrame(parent, text="Команды", padding="5")
        frame.pack(fill='x', pady=10)

        ttk.Button(frame, text="СТАРТ", command=self.model_flow_sensor.start).grid(
            row=0, column=0, padx=5, pady=2)
        ttk.Button(frame, text="СТОП", command=self.model_flow_sensor.stop).grid(
            row=0, column=1, padx=5, pady=2)
        ttk.Button(frame, text="СОХР.FLASH", command=self.model_flow_sensor.save_to_flash).grid(
            row=0, column=2, padx=5, pady=2)

        ttk.Button(frame, text="ОТКРЫТО", command=self.model_flow_sensor.open).grid(
            row=1, column=0, padx=5, pady=2)
        ttk.Button(frame, text="ЗАКРЫТО", command=self.model_flow_sensor.close).grid(
            row=1, column=1, padx=5, pady=2)
        ttk.Button(frame, text="СРЕДНЕЕ", command=self.model_flow_sensor.move_middle).grid(
            row=1, column=2, padx=5, pady=2)

        ttk.Button(frame, text="ПОЗИЦИЯ", command=self.model_flow_sensor.set_position).grid(
            row=2, column=0, padx=5, pady=2)

        ttk.Button(frame, text="ЗВУК", command=self.model_flow_sensor.sound).grid(
            row=2, column=1, padx=5, pady=2)

        # ttk.Button(frame, text="Мелодия", command=self._play_beep_melody).grid(
        #     row=2, column=2, padx=5, pady=2
        # )

        for i in range(3):
            frame.grid_columnconfigure(i, weight=1)

    def _create_log_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Журнал команд", padding=5)
        frame.pack(fill="both", expand=True)

        self.command_output = scrolledtext.ScrolledText(frame, wrap="word", state="normal")
        self.command_output.pack(fill="both", expand=True)

        self.command_output.tag_config("success", foreground="green")
        self.command_output.tag_config("error", foreground="red")
        self.command_output.tag_config("warning", foreground="orange")
        self.command_output.tag_config("info", foreground="black")
        self.command_output.tag_config("command", foreground="purple")
        self.command_output.tag_config("device", foreground="brown")

        def disable_typing(event):
            if (event.state & 0x4) and event.keysym in ("c", "a"):
                return
            return "break"
        self.command_output.bind("<Key>", disable_typing)

        menu = tk.Menu(self.command_output, tearoff=0)
        menu.add_command(label="Копировать", command=lambda: self.command_output.event_generate("<<Copy>>"))
        menu.add_command(label="Выделить всё", command=lambda: self.command_output.tag_add("sel", "1.0", "end"))
        self.command_output.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    # ---------------- Логика ----------------
    def _refresh_ports(self):
        ports = self.model_auger.list_ports()
        if not ports:
            ports = ["Нет портов"]
        self.port_combo["values"] = ports
        self.port_combo_desint["values"] = ports
        if ports:
            self.port_var.set(ports[0])
            self.port_var_desint.set(ports[0])

    def _find_device(self):
        port = self.model_auger.find_device()
        if port:
            self.port_var.set(port)
            self.append_command_log(f"✅ Устройство найдено на {port}")
        else:
            self.append_command_log("❌ Устройство не найдено")

    def _toggle_connection(self):
        if self.model_auger.is_connected():
            self.model_auger.disconnect()
            self.append_command_log("Отключено")
            self.connect_btn.config(text="Подключить")
        else:
            if self.model_auger.connect(self.port_var.get(), self.baud_var.get()):
                self.append_command_log(f"Подключено: {self.port_var.get()} @ {self.baud_var.get()}")
                self.connect_btn.config(text="Отключить")
                self._read_settings()
                self.model_auger.settings_vars = self.setting_vars.copy()
            else:
                messagebox.showerror("Ошибка", "Не удалось подключиться")

        if self.model_flow_sensor.is_connected():
            self.model_flow_sensor.disconnect()
        else:
            if self.model_flow_sensor.connect():
                self.append_command_log(f"Подключено: flow_sensor")

    def _toggle_connection_desint(self):
        if self.desint_model:
            if self.desint_model.is_connected():
                self.desint_model.disconnect()
                self.append_command_log("Отключено")
                self.connect_btn_desint.config(text="Подключить")
            else:
                if self.desint_model.connect(self.port_var_desint, self.baud_var_desint):
                    self.append_command_log(f"Подключено дезинтегратор: {self.port_var_desint.get()} @ "
                                            f"{self.baud_var_desint.get()}")
                self.connect_btn_desint.config(text="Отключить")

    def _set_pressure(self):
        """Устанавливает давление"""
        try:
            self.model_flow_sensor.set_pressure_val(int(float(self.set_pressure_var.get()) * 10))
        except ValueError:
            self.append_command_log("Ошибка: введите число")

    def _read_set_pressure(self):
        try:
            self.set_pressure_var.set(self.model_flow_sensor.read_set_pressure())
        except Exception as e:
            self.append_command_log(f"Ошибка чтения давления: {e}")

    def _apply_settings(self):
        self.model_auger.apply_settings(self.setting_vars)
        # for name, var in self.setting_vars.items():
        #     value = var.get()
        #     ok, msg = self.model.apply_setting(name, value)
        #     self.append_command_log(msg)

    def _read_settings(self):
        settings = self.model_auger.read_settings(self.setting_vars)
        for name, val in settings.items():
            if name in self.setting_vars:
                self.setting_vars[name].set(val)

    def _update_status(self):
        status = self.model_auger.status_flags
        for name, val in status.items():
            if name in self.status_vars:
                self.status_vars[name].set(val)

        self.inning_speed.set(self.model_auger.get_speed_m1())
        self.rotate_speed.set(self.model_auger.get_speed_m2())

        work_time = self.model_auger.get_work_time()
        position = self.model_auger.position
        if work_time is not None:
            self.interval_work_auger.set(f"Время подачи пробы: {round(work_time, 1)} c")

        self.position_work_auger.set(f"Осталось пробы: {round(350 - position)} мг")
        self.progress['value'] = min(round(position / 350 * 100), 100)

        self.model_auger.increase_back_speed = self.increase_back_speed.get()
        self.model_auger.manual = self.manual.get()
        self.model_auger.puring_end = self.puring_end.get()
        self.model_auger.purge_count = self.purge_count.get()
        self.append_command_log_queue()

        style = 'Start.TButton' if self.model_auger.is_valve2_on() else 'Stop.TButton'
        self.switch_v2.config(style=style)

        status = self.model_flow_sensor.status_flags
        for name, val in status.items():
            if name in self.status_vars_flow_sensor:
                self.status_vars_flow_sensor[name].set(val)

        pressure = self.model_flow_sensor.last_values_named['PRESSURE']
        if pressure is not None:
            self.measured_pressure_var.set(f"{pressure} Pa")
        temperature = self.model_flow_sensor.last_values_named['TEMPERATURE']
        if temperature is not None:
            self.temperature_var.set(f"{temperature} °C")
        position = self.model_flow_sensor.last_values_named['POSITION']
        if position is not None:
            self.position_text_var.set(f"Позиция изм.: {position}")

    def _update_interval_upd_data(self, interval):
        self.interval_upd_data.set(f"Обновление данных: {interval}мс")

    def _start_background_tasks(self):
        start_time = time.time()
        self._update_status()

        processing_time = time.time() - start_time
        next_interval = max(2, int(processing_time * 1000 * 1.1))
        self.interval_polling.set(f"Обновление окна: {int(next_interval)}мс")

        if self.window.winfo_exists():
            self.window.after(next_interval, self._start_background_tasks)

    def append_command_log(self, message: str, msg_type="info"):
        self.comand_loger_queue.append([message, msg_type])

    def append_command_log_queue(self):
        for message, msg_type in self.comand_loger_queue:
            self.command_output.insert("end", message + "\n")
            self.command_output.see("end")
            start_index = f"end-{len(message) + 2}c"  # +1 для символа новой строки
            end_index = "end-1c"
            self.command_output.tag_add(msg_type, start_index, end_index)
        self.comand_loger_queue.clear()

    def run(self):
        self.window.mainloop()
