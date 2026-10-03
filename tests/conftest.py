import os
import socket

import pytest

os.environ['OFFLINE'] = '1'  # before pipeline.common is imported: cache misses raise


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise RuntimeError('tests must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', guard)
    monkeypatch.setattr(socket, 'create_connection', guard)
