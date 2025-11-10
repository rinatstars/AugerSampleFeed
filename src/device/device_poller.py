import time
import threading
import queue
from src.device.serial_device_controller import SerialDeviceController


class DevicePoller:
    """Полностью безопасный опросщик устройств"""

    def __init__(self, controller: SerialDeviceController, interval=0.01):
        self.controller = controller
        self.polling_config = None
        self.interval = interval
        self.running = False
        self.thread = None

        # Очереди для передачи данных в главный поток
        self.data_queue = queue.Queue()
        self.callback_queue = queue.Queue()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def init_polling_config(self, polling_config):
        with self._lock:
            self.polling_config = polling_config

    def start(self):
        if self.polling_config is None:
            return False

        if self.running:
            return False

        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(
            target=self._polling_loop,
            name="SafeDevicePoller",
            daemon=True
        )
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None

    def get_new_data(self):
        """Вызывается из главного потока для получения новых данных"""
        data = {}
        while not self.data_queue.empty():
            try:
                addr, value = self.data_queue.get_nowait()
                data[addr] = value
                self.data_queue.task_done()
            except queue.Empty:
                break
        return data

    def process_callbacks(self):
        """Вызывается из главного потока для обработки callback'ов"""
        processed = 0
        while not self.callback_queue.empty():
            try:
                callback_type, data = self.callback_queue.get_nowait()
                # Здесь можно обработать callback'и если нужно
                self.callback_queue.task_done()
                processed += 1
            except queue.Empty:
                break
        return processed

    def _polling_loop(self):
        """Основной цикл опроса - ТОЛЬКО чтение данных, никаких callback'ов"""
        while self.running and not self._stop_event.is_set():
            try:
                if not self.controller.is_connected():
                    time.sleep(0.1)
                    continue

                # Читаем конфигурацию опроса
                with self._lock:
                    if self.polling_config is None:
                        time.sleep(0.1)
                        continue
                    current_config = list(self.polling_config)

                # Опрашиваем устройства
                for addr, _ in current_config:
                    if not self.running:
                        break

                    try:
                        val = self.controller.read_register(addr)
                        if val is not None:
                            # Отправляем данные в очередь для главного потока
                            self.data_queue.put((addr, val))
                    except Exception as e:
                        print(f"[SafeDevicePoller] Ошибка чтения 0x{addr:02X}: {e}")

                    if self.interval > 0:
                        time.sleep(self.interval)

            except Exception as e:
                print(f"[SafeDevicePoller] Критическая ошибка: {e}")
                time.sleep(0.1)