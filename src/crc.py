"""Модуль для вычисления CRC7"""

from src.constants import CRC7_POLYNOMIAL


def gen_crc7_table():
    """Генерирует таблицу для вычисления CRC7."""
    table = [0] * 128
    for i in range(128):
        sum_val = i
        for _ in range(7):
            sum_val = (sum_val << 1) & 0xFF
            if sum_val & 0x80:
                sum_val ^= CRC7_POLYNOMIAL
        table[i] = sum_val & 0xFF
    return table


CRC7_TABLE = gen_crc7_table()


def crc7_generate(packet):
    """Вычисляет CRC7 для кадра (первые 4 байта)."""
    crc7_accum = 0
    for byte in packet[:4]:
        b = byte & 0x7F  # Используем только 7 младших битов
        index = ((crc7_accum << 1) ^ b) & 0x7F
        crc7_accum = CRC7_TABLE[index]
    return crc7_accum