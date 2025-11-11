import time
import threading
from typing import Union
from src.device.serial_device_controller import SerialDeviceController
from src.device.device_controller import DeviceController


class DevicePoller:
    """Фоновый опрос устройства в отдельном потоке"""

    def __init__(self, controller: Union[SerialDeviceController, DeviceController], interval=0.01):
        """
        :param controller: экземпляр SerialDeviceController
        :param interval: задержка между регистрами
        """
        self.controller = controller
        self.polling_config = None
        self.interval = interval
        self.running = False
        self.thread = None
        self.func_calc_time = None
        self.func_calc_update_from_poller = None
        self.start_polling_time = 0

    def init_polling_config(self, polling_config):
        self.polling_config = polling_config

    def start(self):
        if self.polling_config is not None:
            if self.running:
                return
            self.running = True
            self.start_polling_time = time.time()
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            return True
        else:
            return False

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.thread = None

    def _loop(self):
        while self.running:
            try:
                for addr, q in self.polling_config:
                    val = self.controller.read_register(addr)
                    if val is not None:
                        if q.full():
                            q.get()
                        q.put((addr, val))
                    time.sleep(self.interval)

                # время цикла
                period = int((time.time() - self.start_polling_time) * 1000)
                self.start_polling_time = time.time()
                if self.func_calc_time:
                    self.func_calc_time(period)
                if self.func_calc_update_from_poller:
                    self.func_calc_update_from_poller()

            except Exception as e:
                print(f"[DevicePoller] Ошибка: {e}")

    def init_func_time_calc(self, func):
        """Передаём callback для отчёта времени цикла"""
        self.func_calc_time = func

    def init_func_calc_update_from_poller(self, func):
        """Передаём callback для отчёта времени цикла"""
        self.func_calc_update_from_poller = func
