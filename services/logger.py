import logging
import sys
from logging.handlers import TimedRotatingFileHandler
import os

def setup_logger(level="INFO"):
    if not os.path.exists("logs"):
        os.makedirs("logs")

    logger = logging.getLogger()
    logger.setLevel(level)

    # Формат
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
    )

    # Вывод в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Вывод в файл с ротацией
    file_handler = TimedRotatingFileHandler(
        "logs/bot.log", when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Отдельный файл ошибок
    error_handler = TimedRotatingFileHandler(
        "logs/errors.log", when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger