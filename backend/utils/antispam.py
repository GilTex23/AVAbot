import datetime
import logging

class AntiSpamNotify:
    def __init__(self, logger: logging.Logger):
        self.__last_notify_timestamp = None
        self.__failed_requests = 0
        self.logger = logger

    def is_notified(self):
        if self.__last_notify_timestamp:
            passed_ = datetime.datetime.now() - self.__last_notify_timestamp
            if passed_.days == 0:
                return True
        return False

    def set_notify_timestamp(self):
        self.__last_notify_timestamp = datetime.datetime.now()

    @property
    def failed_requests(self):
        return self.__failed_requests

    @failed_requests.setter
    def failed_requests(self, value):
        if value > 0:
            self.__failed_requests += value
        else:
            self.logger.error(f"ValueError in failed_requests.setter. Value: {value}")