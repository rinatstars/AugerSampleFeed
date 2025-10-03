# logger.py
"""Модуль для логирования данных в Excel"""

import pandas as pd
from pathlib import Path
import logging
import time
import os

class DataLogger:
    def __init__(self, log_interval=60):
        """
        Инициализация логгера

        :param log_interval: интервал сохранения данных в секундах (по умолчанию 60)
        """
        self.log_interval = log_interval
        self.last_log_time = time.time()
        self.log_data = []
        self._init_logging()
        self.batch_mode = False  # Режим пакетного добавления

    def _init_logging(self):
        """Инициализация системы логирования"""
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "device_data_log.xlsx"

        # Создаем файл с заголовками, если его нет
        if not self.log_file.exists():
            df = pd.DataFrame(columns=[
                "Timestamp",
                "Temperature (°C)",
                "Pressure (Pa)",
                "Position",
                "Status"
            ])
            df.to_excel(self.log_file, index=False, engine='openpyxl')

    def start_batch(self):
        """Начинает пакетное добавление данных"""
        self.batch_mode = True
        self.batch_data = []

    def add_data(self, timestamp, temperature, pressure, position, status):
        """
        Добавление данных в буфер логгера

        :param timestamp: метка времени
        :param temperature: значение температуры
        :param pressure: значение давления
        :param position: позиция заслонки
        :param status: статус устройства (битовая маска)
        """
        self.log_data.append([
            timestamp,
            float(temperature) if temperature is not None else None,
            float(pressure) if pressure is not None else None,
            position,
            status
        ])

        # Проверяем, нужно ли сохранять данные
        if time.time() - self.last_log_time >= self.log_interval:
            self._save_data()
            self.last_log_time = time.time()
            self.log_data = []

    def _save_data(self):
        """Сохранение накопленных данных в Excel файл"""
        if not self.log_data:
            return

        try:
            # Создаем временный файл
            temp_file = self.log_file.with_suffix('.tmp')

            # Читаем существующие данные
            if os.path.exists(self.log_file):
                try:
                    existing_data = pd.read_excel(self.log_file, engine='openpyxl')
                except:
                    existing_data = pd.DataFrame(columns=[
                        "Timestamp",
                        "Temperature (°C)",
                        "Pressure (Pa)",
                        "Position",
                        "Status"
                    ])
            else:
                existing_data = pd.DataFrame(columns=[
                    "Timestamp",
                    "Temperature (°C)",
                    "Pressure (Pa)",
                    "Position",
                    "Status"
                ])

            # Добавляем новые данные
            new_data = pd.DataFrame(self.log_data, columns=existing_data.columns)
            combined_data = pd.concat([existing_data, new_data], ignore_index=True)

            # Сохраняем во временный файл
            combined_data.to_excel(temp_file, index=False, engine='openpyxl')

            # Заменяем старый файл новым
            if os.path.exists(self.log_file):
                os.replace(temp_file, self.log_file)
            else:
                temp_file.rename(self.log_file)

            logging.info(f"Данные успешно сохранены в {self.log_file}")

        except Exception as e:
            logging.error(f"Ошибка при сохранении в Excel: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def flush(self):
        """Принудительное сохранение данных, если буфер не пуст"""
        if self.log_data:
            self._save_data()
            self.log_data = []
            self.last_log_time = time.time()