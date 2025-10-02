"""Основной модуль приложения"""

import json
import sys
from pathlib import Path
from serial_device_controller import SerialDeviceController
from gui import DeviceGUI


def load_config(config_path="config.json"):
    """Загрузка настроек устройства из JSON-файла"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """Точка входа в приложение"""
    try:
        config = load_config()
    except FileNotFoundError:
        # дефолтные настройки, если нет файла
        config = {
            "port": "COM3",
            "baudrate": 38400,
            "device_id": 3,
            "MOTOR_SPEED_1": 137270,
            "MOTOR_SPEED_2": 1405000
        }

    controller = SerialDeviceController(
        port=config.get("port", "COM3"),
        baudrate=config.get("baudrate", 38400),
        device_id=config.get("device_id", 3),
    )

    app = DeviceGUI(controller, config)

    # перенаправим stdout/stderr в лог GUI
    class GuiOutputRedirector:
        def __init__(self, gui):
            self.gui = gui

        def write(self, message):
            if message.strip():
                self.gui.append_command_log(message.strip())

        def flush(self):
            pass

    sys.stdout = GuiOutputRedirector(app)
    sys.stderr = GuiOutputRedirector(app)

    app.run()


if __name__ == "__main__":
    main()
