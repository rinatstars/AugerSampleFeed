import tkinter as tk
import time
import sys
import os
from tkinter import ttk, scrolledtext, messagebox, StringVar
import serial.tools.list_ports
from constants import (
    REG_STATUS, REG_CONTROL, REG_VERIFY,
    REG_COM_M1, REG_COM_M2,
    CMD_NULL, CMD_START,
    MOTOR_CMD_START_FWD, MOTOR_CMD_START_BACK, MOTOR_CMD_STOP,
    VERIFY_CODE, REGISTERS_MAP
)


def resource_path(relative_path):
    """Определяет путь к ресурсам в .exe и при запуске из исходников"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class DeviceGUI:
    def __init__(self, controller):
        self.controller = controller
        self.window = tk.Tk()
        self.window.title("Auger sample introduction system")
        self.window.geometry("900x650")
        self.window.iconbitmap(resource_path("icon.ico"))
        self.interval_polling = StringVar(value="Обновление окна: ---мс")
        self.interval_upd_data = StringVar(value="Обновление данных: ---мс")
        self._setup_ui()
        self._start_background_tasks()
        self.controller.init_func_time_culc(self._update_interval_upd_data)


    def _setup_ui(self):
        main_container = ttk.Frame(self.window, padding="10")
        main_container.pack(fill="both", expand=True)
        main_container.columnconfigure(0, weight=0)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)

        # Левая колонка
        left_frame = ttk.Frame(main_container)
        left_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        # Правая колонка
        right_frame = ttk.Frame(main_container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Подключение
        self._create_connection_frame(left_frame)

        # Статус
        self._create_status_frame(left_frame)

        # Настройки
        self._create_settings_frame(left_frame)

        # Управление
        self._create_control_frame(left_frame)

        # Верификация
        self._create_verify_frame(left_frame)

        # Связь
        self._create_ping_frame(left_frame)

        # Журнал команд
        self._create_log_frame(right_frame)

    def _create_connection_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Подключение", padding=5)
        frame.pack(fill="x", pady=5)

        # Получаем список доступных портов
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["Нет портов"]

        ttk.Label(frame, text="Порт:").grid(row=0, column=0, sticky="w")

        self.port_var = tk.StringVar(value=ports[0])
        self.port_combo = ttk.Combobox(frame, textvariable=self.port_var, values=ports, width=12, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=2, pady=2)

        # Кнопка обновления списка
        refresh_btn = ttk.Button(frame, text="⟳", width=3, command=self._refresh_ports)
        refresh_btn.grid(row=0, column=2, padx=2)

        ttk.Label(frame, text="Baudrate:").grid(row=0, column=3, sticky="w")
        self.baud_var = tk.IntVar(value=self.controller.baudrate)
        ttk.Entry(frame, textvariable=self.baud_var, width=8).grid(row=0, column=4, padx=2)

        self.connect_btn = ttk.Button(frame, text="Подключить", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)


    def _create_status_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Статус", padding=5)
        frame.pack(fill="x", pady=5)

        self.status_vars = {}
        bits = [
            "START", "BEG_BLK", "END_BLK", "M1_FWD", "M1_BACK",
            "M2_FWD", "M2_BACK", "VALVE1_ON", "VALVE2_ON", "RESET", "PING"
        ]
        for i, bit in enumerate(bits):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(frame, text=bit, variable=var, state="disabled")
            cb.grid(row=i // 2, column=i % 2, sticky="w")
            self.status_vars[bit] = var

    def _create_settings_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Настройки", padding=5)
        frame.pack(fill="x", pady=5)

        self.settings_vars = {}
        settings = [
            ("SET_PERIOD_M1", 1000),
            ("SET_PERIOD_M2", 1000),
            ("PERIOD_M1", 1000),
            ("PERIOD_M2", 1000),
            ("T_START", 500),
            ("T_GRIND", 500),
            ("T_PURGING", 500),
        ]

        for i, (name, default) in enumerate(settings):
            ttk.Label(frame, text=name).grid(row=i if i < len(settings)/2 else i - round(len(settings)/2),
                                             column=0 if i < len(settings)/2 else 2, sticky="w")
            var = tk.IntVar(value=default)
            spin = ttk.Spinbox(frame, from_=0, to=100000, increment=100, textvariable=var, width=10)
            spin.grid(row=i if i < len(settings)/2 else i - round(len(settings)/2),
                      column=1 if i < len(settings)/2 else 3, sticky="w")
            self.settings_vars[name] = var

        ttk.Button(frame, text="Применить", command=self._apply_settings).grid(
            row=len(settings), column=0, columnspan=2, pady=5)
        ttk.Button(frame, text="Прочитать", command=self._read_settings).grid(row=len(settings), column=1,
                                                                               columnspan=2, pady=5)

    def _create_control_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Управление", padding=5)
        frame.pack(fill="x", pady=5)

        ttk.Button(frame, text="СТАРТ", command=lambda: self._send_command(REG_CONTROL, CMD_START)).grid(row=0, column=0, padx=5)
        ttk.Button(frame, text="СТОП", command=lambda: self._send_command(REG_CONTROL, CMD_NULL)).grid(row=0, column=1, padx=5)

        ttk.Label(frame, text="Мотор 1:").grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=lambda: self._send_command(REG_COM_M1, MOTOR_CMD_START_FWD)).grid(row=1, column=1)
        ttk.Button(frame, text="Назад", command=lambda: self._send_command(REG_COM_M1, MOTOR_CMD_START_BACK)).grid(row=1, column=2)
        ttk.Button(frame, text="Стоп", command=lambda: self._send_command(REG_COM_M1, MOTOR_CMD_STOP)).grid(row=1, column=3)

        ttk.Label(frame, text="Мотор 2:").grid(row=2, column=0, sticky="w")
        ttk.Button(frame, text="Вперёд", command=lambda: self._send_command(REG_COM_M2, MOTOR_CMD_START_FWD)).grid(row=2, column=1)
        ttk.Button(frame, text="Назад", command=lambda: self._send_command(REG_COM_M2, MOTOR_CMD_START_BACK)).grid(row=2, column=2)
        ttk.Button(frame, text="Стоп", command=lambda: self._send_command(REG_COM_M2, MOTOR_CMD_STOP)).grid(row=2, column=3)

    def _create_verify_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Верификация", padding=5)
        frame.pack(fill="x", pady=5)

        ttk.Button(frame, text="Проверить устройство", command=self._verify_device).pack()

    def _create_ping_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Связь", padding="5")
        frame.pack(fill='x', pady=5)

        ttk.Label(frame, textvariable=self.interval_polling).grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(frame, textvariable=self.interval_upd_data).grid(row=0, column=1, padx=5, sticky='w')

    def _create_log_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Журнал команд", padding=5)
        frame.pack(fill="both", expand=True)

        self.command_output = scrolledtext.ScrolledText(frame, wrap="word", state="normal")
        self.command_output.pack(fill="both", expand=True)

        # Запрет ввода вручную
        self.command_output.bind("<Key>", lambda e: "break")

    def _refresh_ports(self):
        """Обновляет список доступных COM-портов"""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["Нет портов"]
        self.port_combo["values"] = ports
        if ports:
            self.port_var.set(ports[0])

    def _toggle_connection(self):
        if self.controller.is_connected():
            self.controller.disconnect()
            #self.controller.stop_polling()
            self.append_command_log("Отключено")
            self.connect_btn.config(text="Подключить")
        else:
            if self.controller.connect(self.port_var.get(), self.baud_var.get()):
                #self.controller.start_polling()
                self.append_command_log(f"Подключено: {self.port_var.get()} @ {self.baud_var.get()}")
                self.connect_btn.config(text="Отключить")
            else:
                messagebox.showerror("Ошибка", "Не удалось подключиться")

    def _apply_settings(self):
        if self.controller.is_connected():
            for name, var in self.settings_vars.items():
                value = var.get()
                reg_addr = REGISTERS_MAP.get(name)
                if reg_addr is None:
                    self.append_command_log(f"[!] Неизвестный параметр: {name}")
                    continue

                try:
                    self.controller.write_register(reg_addr, value)
                    self.append_command_log(f"[OK] Установлено {name} = {value} → регистр 0x{reg_addr:02X}")
                except Exception as e:
                    self.append_command_log(f"[ERR] Ошибка при записи {name}: {e}")
        else:
            self.append_command_log(f"[ERR] Устройство не подключено")

    def _read_settings(self):
        if self.controller.is_connected():
            for name, var in self.settings_vars.items():
                reg_addr = REGISTERS_MAP.get(name)
                if reg_addr is None:
                    self.append_command_log(f"[!] Неизвестный параметр: {name}")
                    continue

                try:
                    val = self.controller.read_register(reg_addr)
                    if val:
                        var.set(val)
                        self.append_command_log(f"[OK] Прочитано {name} = {val} → регистр 0x{reg_addr:02X}")
                    else:
                        self.append_command_log(f"[ERR] Ошибка при чтении {name}: значение None")
                except Exception as e:
                    self.append_command_log(f"[ERR] Ошибка при чтении {name}: {e}")
        else:
            self.append_command_log(f"[ERR] Устройство не подключено")

    def _send_command(self, reg, value):
        try:
            if self.controller.write_register(reg, value):
                self.append_command_log(f"Отправлено: {reg=} {value=}")
        except Exception as e:
            self.append_command_log(f"Ошибка отправки: {e}")

    def _verify_device(self):
        try:
            val = self.controller.read_register(REG_VERIFY)
            if val == VERIFY_CODE:
                self.append_command_log("Устройство опознано ✅")
            else:
                self.append_command_log(f"Ошибка: код {val}, ожидалось {VERIFY_CODE}")
        except Exception as e:
            self.append_command_log(f"Ошибка чтения: {e}")

    def _update_status(self):
        """Обновляет статусные флаги"""
        while not self.controller.status_queue.empty():
            address, value = self.controller.status_queue.get()
            if address == REG_STATUS:
                for i, (name, var) in enumerate(self.status_vars.items()):
                    var.set(bool(value & (1 << i)))


    def _update_interval_upd_data(self, interval):
        self.interval_upd_data.set(f"Обновление данных: {interval}мс")


    def _start_background_tasks(self):
        """Оптимизированный планировщик задач"""
        start_time = time.time()

        # Обновляем данные
        self._update_status()

        # Динамически регулируем интервал
        processing_time = time.time() - start_time
        next_interval = max(2, int(processing_time * 1000 * 1.1))  # +10% к времени обработки
        self.interval_polling.set(f"Обновление окна: {int(next_interval)}мс")

        if self.window.winfo_exists():
            self.window.after(next_interval, self._start_background_tasks)

    def append_command_log(self, message: str):
        self.command_output.insert("end", message + "\n")
        self.command_output.see("end")

    def run(self):
        self.window.mainloop()
