"""Основной модуль приложения"""

import json
import sys
import queue
from pathlib import Path
from src.device.serial_device_controller import SerialDeviceController
from src.device.device_controller import DeviceController
from src.gui.gui import DeviceGUI
from src.device.device_poller import DevicePoller
from src.device.device_model import DeviceModelAuger
from src.device.device_model_flow_sensor import DeviceModelFlowSensor
from src.fireballProxy.fireballProxy import FireballProxy
from src.device.Desint_controller import ArduinoDesint


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
        config_auger = load_config(config_path="config_auger.json")
    except FileNotFoundError:
        # дефолтные настройки, если нет файла
        config_auger = {
            "port": "COM3",
            "baudrate": 38400,
            "device_id": 3,
            "MOTOR_SPEED_1": 97690,
            "MOTOR_SPEED_2": 1405000
        }

    try:
        config_flow_sensor = load_config(config_path="config_flow_sensor.json")
    except FileNotFoundError:
        # дефолтные настройки, если нет файла
        config_flow_sensor = {
            "ip": "10.116.220.101",
            "port": 10555,
            "device_id": 3,
            "max_attempts": 5,
            "poll_interval_sec": 2
        }

    controllerAuger = SerialDeviceController(
        port=config_auger.get("port", "COM3"),
        baudrate=config_auger.get("baudrate", 38400),
        device_id=config_auger.get("device_id", 3),
    )

    controllerFlowSensor = DeviceController(
        ip=config_flow_sensor.get("ip", "10.116.220.101"),
        port=config_flow_sensor.get("device_id", 10555),
        device_id=config_flow_sensor.get("device_id", 3)
    )

    # Создаем poller
    pollerAuger = DevicePoller(controllerAuger, interval=0.005)
    pollerFlowSensor = DevicePoller(controllerFlowSensor, interval=0.005)

    desint = ArduinoDesint()
    modelFlowSensor = DeviceModelFlowSensor(controllerFlowSensor, poller=pollerFlowSensor)
    modelAuger = DeviceModelAuger(controllerAuger, config_auger, pollerAuger, desint, modelFlowSensor)

    app = DeviceGUI(model_auger=modelAuger, desint_model=desint, model_flow_sensor=modelFlowSensor)

    # очередь для команд из FireballProxy
    cmd_queue = queue.Queue()

    # инициализация прокси
    proxy = FireballProxy(
        claim_class="TDForm",
        claim_name="Генератор тока",
        forward_name="Генератор токла",
        command_queue=cmd_queue,
        model=modelAuger,
        desint_model=desint,
        flow_sensor_model=modelFlowSensor
    )
    proxy.start()

    # функция обработки команд из очереди
    def process_commands():
        while not cmd_queue.empty():
            try:
                cmd = cmd_queue.get_nowait()
                if cmd == "START":
                    app.start_process()
                elif cmd == "STOP":
                    app.stop_process()
            except Exception as e:
                print(f'[ERROR] process_commands: {e}')
                app.stop_process()

        app.window.after(100, process_commands)

    # запуск цикла обработки команд
    app.window.after(100, process_commands)

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
