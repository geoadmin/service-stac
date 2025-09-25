from logging.handlers import QueueListener


class AutoStartQueueListener(QueueListener):

    def __init__(self, queue, *handlers, respect_handler_level=False):
        super().__init__(queue, *handlers, respect_handler_level=respect_handler_level)
        self.start()
