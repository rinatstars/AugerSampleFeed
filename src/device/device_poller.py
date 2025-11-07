import time
import threading
from src.device.serial_device_controller import SerialDeviceController


class DevicePoller:
    """Фоновый опрос устройства в отдельном потоке"""

    def __init__(self, controller: SerialDeviceController, interval=0.01):
        """
        :param controller: экземпляр SerialDeviceController
        :param polling_config: список (addr, queue)
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

        self._lock = threading.Lock()

    def init_polling_config(self, polling_config):
        with self._lock:
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
        """Основной цикл опроса с обработкой исключений GIL"""
        while self.running:
            try:
                # Создаем локальную копию конфигурации для thread safety
                with self._lock:
                    current_config = self.polling_config.copy() if self.polling_config else []

                for addr, q in current_config:
                    if not self.running:  # Проверяем флаг после каждой операции
                        break

                    # Чтение регистра - здесь может возникать проблема с GIL
                    val = self.controller.read_register(addr)

                    if val is not None and self.running:
                        # Безопасная работа с очередью
                        if q.full():
                            try:
                                q.get_nowait()
                            except:
                                pass
                        q.put((addr, val))

                    time.sleep(self.interval)

                # Вызов callback'ов - убеждаемся что они существуют
                if self.running:
                    period = int((time.time() - self.start_polling_time) * 1000)
                    self.start_polling_time = time.time()

                    if self.func_calc_time:
                        try:
                            self.func_calc_time(period)
                        except Exception as e:
                            print(f"[DevicePoller] Ошибка в func_calc_time: {e}")

                    if self.func_calc_update_from_poller:
                        try:
                            self.func_calc_update_from_poller()
                        except Exception as e:
                            print(f"[DevicePoller] Ошибка в func_calc_update_from_poller: {e}")

            except Exception as e:
                print(f"[DevicePoller] Критическая ошибка: {e}")
                time.sleep(0.1)  # Задержка при критических ошибках

    def init_func_time_calc(self, func):
        """Передаём callback для отчёта времени цикла"""
        self.func_calc_time = func

    def init_func_calc_update_from_poller(self, func):
        """Передаём callback для отчёта времени цикла"""
        self.func_calc_update_from_poller = func