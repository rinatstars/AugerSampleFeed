"""Модуль с константами и настройками"""

# Константы для CRC7
CRC7_POLYNOMIAL = 0x89  # x^7 + x^3 + 1

"""Модуль с константами и настройками для устройства по RS232 (VMK Protocol)"""

# Настройки подключения
DEFAULT_PORT = "COM3"        # или "/dev/ttyUSB0" для Linux
DEFAULT_BAUDRATE = 38400
DEFAULT_DEVICE_ID = 0x03     # Адрес устройства (MY_ADDRESS)
READ_TIMEOUT = 2.0
WRITE_TIMEOUT = 2.0

# Адреса регистров
REG_STATUS = 0x00
REG_CONTROL = 0x01
REG_COM_M1 = 0x02
REG_COM_M2 = 0x03
REG_SET_PERIOD_M1 = 0x04
REG_SET_PERIOD_M2 = 0x05
REG_PERIOD_M1 = 0x06
REG_PERIOD_M2 = 0x07
REG_T_START = 0x08
REG_T_GRIND = 0x09
REG_T_PURGING = 0x0A

REG_VERIFY = 0x20
VERIFY_CODE = 0x5601  # Код идентификации устройства

# Биты статуса
FS_START = 0
FS_BEG_BLK = 1
FS_END_BLK = 2
FS_M1_FWD = 3
FS_M1_BACK = 4
FS_M2_FWD = 5
FS_M2_BACK = 6
FS_VALVE1_ON = 7
FS_VALVE2_ON = 8
FS_RESET = 14
FS_PING = 15

# Команды для REG_CONTROL
CMD_NULL = 0
CMD_START = 1

# Команды для моторов (REG_COM_M1 / REG_COM_M2)
MOTOR_CMD_NULL = 0
MOTOR_CMD_START_FWD = 1
MOTOR_CMD_START_BACK = 2
MOTOR_CMD_STOP = 3

REGISTERS_MAP = {
    "SET_PERIOD_M1": REG_SET_PERIOD_M1,
    "SET_PERIOD_M2": REG_SET_PERIOD_M2,
    "PERIOD_M1": REG_PERIOD_M1,
    "PERIOD_M2": REG_PERIOD_M2,
    "T_START": REG_T_START,
    "T_GRIND": REG_T_GRIND,
    "T_PURGING": REG_T_PURGING,
}

# Перевод скоростей

