from abc import ABC, abstractmethod


class Agent(ABC):

    name = "base"

    def __init__(self, router, memory, logger):
        self.router = router
        self.memory = memory
        self.logger = logger

    @abstractmethod
    def run(self, *args, **kwargs):
        raise NotImplementedError
