import tkinter as tk
import time
import sys
from pathlib import Path
from tkinter import ttk, scrolledtext, messagebox, StringVar, BooleanVar
from src.device.device_model import DeviceModel


def resource_path(relative: str) -> str:
    """Возвращает абсолютный путь к ресурсу (иконке, файлу и т.п.)"""
    base_path = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent.parent)
    base_path = Path(base_path)  # гарантируем Path
    return str(base_path / relative)


class DeviceGUI:
    def __init__(self, model, desint_model=None):
        """
        :param model: экземпляр DeviceModel
        param desint_model: экземпляр ArduinoDesint
        """
        self.model: DeviceModel = model
        self.desint_model = desint_model
        self.model.init_command_loger(self.append_command_log)

        self.window = tk.Tk()
        self.window.title("Auger sample introduction system")
        self.window.geometry("900x950")
        icon_path = resource_path("icon.ico")
        self.window.iconbitmap(icon_path)

        self.interval_polling = StringVar(value="Обновление окна: ---мс")
        self.interval_upd_data = StringVar(value="Обновление данных: ---мс")
        self.interval_work_auger = StringVar(value="Время подачи пробы: ---с")
        self.position_work_auger = StringVar(value="Положение шнека: ---мм")

        self._setup_ui()
        self._start_background_tasks()

        if self.model.poller is not None:
            self.model.poller.init_func_time_calc(self._update_interval_upd_data)

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

        right_frame = ttk.Frame(main_container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        self._create_connection_frame(left_frame)
        self._create_connection_desint_frame(left_frame)
        self._create_status_frame(left_frame)
        self._create_settings_frame(left_frame)
        self._create_control_frame(left_frame)
        self._create_desint_frame(left_frame)
        self._create_verify_frame(left_frame)
        self._create_ping_frame(left_frame)
        self._create_time_work_frame(left_frame)
        self._create_log_frame(right_frame)
        self._setup_keyboard_bindings()

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

        if key == 'space' and self.model.is_connected():
            self.model.start_process()
            self.append_command_log('Запуск по пробелу')

    def _create_connection_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Подключение", padding=5)
        frame.pack(fill="x", pady=5)

        ports = self.model.list_ports()
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
        self.baud_var = tk.IntVar(value=self.model.config.get("baudrate", 38400))
        ttk.Entry(frame, textvariable=self.baud_var, width=8).grid(row=0, column=4, padx=2)

        self.connect_btn = ttk.Button(frame, text="Подключить", command=self._toggle_connection)
        self.connect_btn.grid(row=1, column=0, columnspan=2, padx=5)

        # Кнопка найти устройство
        find_btn = ttk.Button(frame, text="Найти устройство", command=self._find_device)
        find_btn.grid(row=1, column=2, columnspan=3, padx=5)

    def _create_connection_desint_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Подключение дезинтегратора", padding=5)
        frame.pack(fill="x", pady=5)

        ports = self.model.list_ports()
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
        for i, bit in enumerate(self.model.status_flags):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(frame, text=bit, variable=var, state="disabled")
            cb.grid(row=i // 4, column=i % 4, sticky="w")
            self.status_vars[bit] = var

        ttk.Label(frame, text="Подача, мм/мин").grid(row=3, column=0, sticky="w")
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

        for i, (name, meta) in enumerate(self.model.settings.items()):
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
                    init_val = self.model.speed_to_period_m1(meta["default"])
                else:
                    init_val = self.model.speed_to_period_m2(meta["default"])
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
                    self.setting_vars_raw[name].set(self.model.speed_to_period_m1(val))
                else:
                    self.setting_vars_raw[name].set(self.model.speed_to_period_m2(val))
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
                    self.setting_vars[name].set(round(self.model.period_to_speed_m1(val), 2))
                else:
                    self.setting_vars[name].set(round(self.model.period_to_speed_m2(val), 2))
            finally:
                self._syncing = False

    def _create_control_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Управление", padding=5)
        frame.pack(fill="x", pady=5)

        ttk.Button(frame, text="СТАРТ", command=self.start_process).grid(row=0, column=0, padx=5)

        ttk.Button(frame, text="СТАРТ Ручн.", command=self.start_process_manual).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="СТОП", command=self.stop_process_manual).grid(row=0, column=2, padx=5)
        ttk.Button(frame, text="НАЗАД", command=self.model.go_back).grid(row=0, column=3, padx=5)

        ttk.Label(frame, text="Мотор 1:").grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=self.model.motor1_forward).grid(row=1, column=1)
        ttk.Button(frame, text="Назад", command=self.model.motor1_backward).grid(row=1, column=2)
        ttk.Button(frame, text="Стоп", command=self.model.motor1_stop).grid(row=1, column=3)

        ttk.Label(frame, text="Мотор 2:").grid(row=2, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=self.model.motor2_forward).grid(row=2, column=1)
        ttk.Button(frame, text="Назад", command=self.model.motor2_backward).grid(row=2, column=2)
        ttk.Button(frame, text="Стоп", command=self.model.motor2_stop).grid(row=2, column=3)

        ttk.Label(frame, text="Клапан 1:").grid(row=3, column=0, sticky="w")
        ttk.Button(frame, text="Открыть", command=self.model.valve1_on).grid(row=3, column=1)
        ttk.Button(frame, text="Закрыть", command=self.model.valve1_off).grid(row=3, column=2)

        ttk.Label(frame, text="Клапан 2:").grid(row=4, column=0, sticky="w")
        ttk.Button(frame, text="Открыть", command=self.model.valve2_on).grid(row=4, column=1)
        ttk.Button(frame, text="Закрыть", command=self.model.valve2_off).grid(row=4, column=2)

        self.increase_back_speed = BooleanVar(value=True)
        self.manual = BooleanVar(value=True)
        self.puring_end = BooleanVar(value=True)
        ttk.Label(frame, text="Настройка:").grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(frame, text='Ускорить назад', variable=self.increase_back_speed).grid(row=6, column=1)
        ttk.Checkbutton(frame, text='Ручной старт', variable=self.manual).grid(row=6, column=2)
        ttk.Checkbutton(frame, text='Ручной старт', variable=self.puring_end).grid(row=6, column=3)

    def start_process(self):
        if self.manual.get():
            self.start_process_manual()
            return
        self.model.start_process()
        if self.on_desint.get():
            self.desint_model.send_start()

    def stop_process(self):
        if self.manual.get():
            self.stop_process_manual()
            return
        self.model.stop_process()
        if self.on_desint.get():
            self.desint_model.send_end()

    def start_process_manual(self):

        self.model.start_process_manual_init(self.on_desint.get())

    def stop_process_manual(self):
        self.model.stop_process_manual()

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
        ttk.Button(frame, text="Проверить устройство", command=self.model.verify_device).pack()

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
        ports = self.model.list_ports()
        if not ports:
            ports = ["Нет портов"]
        self.port_combo["values"] = ports
        self.port_combo_desint["values"] = ports
        if ports:
            self.port_var.set(ports[0])
            self.port_var_desint.set(ports[0])

    def _find_device(self):
        port = self.model.find_device()
        if port:
            self.port_var.set(port)
            self.append_command_log(f"✅ Устройство найдено на {port}")
        else:
            self.append_command_log("❌ Устройство не найдено")

    def _toggle_connection(self):
        if self.model.is_connected():
            self.model.disconnect()
            self.append_command_log("Отключено")
            self.connect_btn.config(text="Подключить")
        else:
            if self.model.connect(self.port_var.get(), self.baud_var.get()):
                self.append_command_log(f"Подключено: {self.port_var.get()} @ {self.baud_var.get()}")
                self.connect_btn.config(text="Отключить")
                self._read_settings()
            else:
                messagebox.showerror("Ошибка", "Не удалось подключиться")

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

    def _apply_settings(self):
        self.model.apply_settings(self.setting_vars)
        # for name, var in self.setting_vars.items():
        #     value = var.get()
        #     ok, msg = self.model.apply_setting(name, value)
        #     self.append_command_log(msg)

    def _read_settings(self):
        settings = self.model.read_settings(self.setting_vars)
        for name, val in settings.items():
            if name in self.setting_vars:
                self.setting_vars[name].set(val)

    def _update_status(self):
        status = self.model.status_flags
        for name, val in status.items():
            if name in self.status_vars:
                self.status_vars[name].set(val)

        self.inning_speed.set(self.model.get_speed_m1())
        self.rotate_speed.set(self.model.get_speed_m2())

        work_time = self.model.get_work_time()
        position = self.model.position
        if work_time is not None:
            self.interval_work_auger.set(f"Время подачи пробы: {round(work_time, 1)} c")

        self.position_work_auger.set(f"Положение шнека: {round(position, 2)} мм")

        if self.desint_model and self.desint_model.is_connected() and self.desint_model.is_running:
            if self.model.is_end_process():
                self.desint_model.send_end()

        self.model.increase_back_speed = self.increase_back_speed.get()
        self.model.manual = self.manual.get()
        self.model.puring_end = self.puring_end.get()

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

    def append_command_log(self, message: str, msg_type: str ='info'):
        self.command_output.insert("end", message + "\n")
        start_index = f"end-{len(message) + 2}c"  # +1 для символа новой строки
        end_index = "end-1c"
        self.command_output.tag_add(msg_type, start_index, end_index)
        self.command_output.see("end")

    def run(self):
        self.window.mainloop()
