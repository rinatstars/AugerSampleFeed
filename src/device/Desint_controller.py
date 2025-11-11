import serial
import time
import threading


class ArduinoDesint:
    def __init__(self, port='COM3', baudrate=9600, timeout=None):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.lock = threading.Lock()
        self.is_running = False
        self.timeon = None
        self.frequence = None

    def connect(self, port=None, baudrate=None):
        if port:
            self.port = port.get()
        if baudrate:
            self.baudrate = baudrate.get()
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)

            print(f"Подключено к Arduino на порту {self.port}")
            response = self.ser.readline().decode().strip()
            if response:
                print(f"Arduino: {response}")
            return True
        except serial.SerialException as e:
            print(f"Ошибка подключения: {e}")
            return False

    def is_connected(self):
        """Проверка состояния соединения"""
        return self.ser is not None and self.ser.is_open

    def set_pwm(self, timeon, frequence):
        """
        Установка скважности ШИМ в процентах для указанного пина
        """
        self.timeon = timeon
        self.frequence = frequence

        if not self.ser or not self.ser.is_open:
            print("Нет соединения с Arduino")
            return False

        base_frequence = 1000 / timeon
        base_frequence = base_frequence / 2
        if frequence > base_frequence:
            frequence = base_frequence

        period = 1000 / frequence
        timeoff = period - timeon


        return self.set_parameters(timeon, timeoff)

    def set_parameters(self, timeon, timeoff):
        with self.lock:
            if not self.is_connected():
                return None
            try:
                command = f"PWM:{timeon}|{timeoff}\n"
                print(command)
                self.ser.write(command.encode())
                response = self.ser.readline().decode().strip()
                if response:
                    trash, timeon = response.split(':')
                    print(response)
                response = self.ser.readline().decode().strip()
                if response:
                    trash, timeoff = response.split(':')
                    print(response)
                return timeon, timeoff
            except Exception as e:
                print(f"[ERROR] set_parameters desint: {e}")
                return None

    def send_start(self):
        with self.lock:
            if not self.is_connected():
                return None
            try:
                command = f"COMAND:1\n"
                self.ser.write(command.encode())
                self.is_running = True
                response = self.ser.readline().decode().strip()
                if response:
                    print(response)
                    return True
            except Exception as e:
                print(f"[ERROR] send_start desint: {e}")
                return None

    def send_end(self):
        with self.lock:
            if not self.is_connected():
                return None
            try:
                command = f"COMAND:0\n"
                self.ser.write(command.encode())
                self.is_running = False
                response = self.ser.readline().decode().strip()
                if response:
                    print(response)
            except Exception as e:
                print(f"Attempt reconnected: {e}")
                self.disconnect()
                self.connect()
                time.sleep(0.5)
                command = f"COMAND:0\n"
                self.ser.write(command.encode())
                self.is_running = False
                response = self.ser.readline().decode().strip()
                if response:
                    print(response)
                else:
                    print('[Error] send_end')
                return None

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Соединение закрыто")