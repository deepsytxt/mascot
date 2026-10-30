import json
import socket

import pytest

from ipc import AlreadyRunning, Server, send


def test_single_instance_command_delivery_and_cleanup(tmp_path):
    messages = []
    with Server(messages.append, tmp_path):
        assert send({'emotion': 'joy', 'text': 'Привет!'}, tmp_path)
        assert messages == [{'emotion': 'joy', 'text': 'Привет!'}]
        with pytest.raises(AlreadyRunning):
            Server(messages.append, tmp_path).start()
    assert not send({'quit': True}, tmp_path)
    with Server(messages.append, tmp_path):
        assert send({'ping': True}, tmp_path)
    assert len(messages) == 1


def test_wrong_token_and_oversize_messages_are_rejected(tmp_path):
    messages = []
    with Server(messages.append, tmp_path):
        endpoint = json.loads((tmp_path / 'endpoint.json').read_text())
        with socket.create_connection(('127.0.0.1', endpoint['port'])) as connection:
            connection.sendall(b'{"token":"wrong","message":{"quit":true}}\n')
            assert json.loads(connection.recv(100)) == {'ok': False}
        assert not send({'text': 'x' * 9000}, tmp_path)
    assert not messages
