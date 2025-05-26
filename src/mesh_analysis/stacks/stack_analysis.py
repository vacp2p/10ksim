from abc import ABC, abstractmethod


class StackAnalysis(ABC):

    def __init__(self, **kwargs):
        self._kwargs = kwargs

    @abstractmethod
    def get_reliability_data(self, n_jobs: int, **kwargs):
        pass