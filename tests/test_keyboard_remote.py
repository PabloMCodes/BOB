"""Remote protocol and input-loss checks without physical motor commands."""
import asyncio
import struct

import pytest

from hardware.esp32.remote import Remote, direction
from hardware.controller_protocol import COMMAND_UUID, encode_stop


class Client:
    def __init__(self):
        self.packets = []

    async def write_gatt_char(self, uuid, packet, response):
        assert uuid == COMMAND_UUID and response
        self.packets.append(packet)

    async def read_gatt_char(self, uuid):
        return struct.pack('<BBBBIIhh', 1, 0, 0, 5, 123, 7, 0, 0)


def test_controller_session_sequence_and_rearm_after_release():
    async def scenario():
        client = Client()
        remote = Remote(client)
        await remote.stop()
        await remote.move('F')
        await remote.move('L')
        await remote.stop()
        await remote.move('B')
        assert [p[1] for p in client.packets] == [0, 1, 2, 2, 0, 1, 2]
        assert struct.unpack('<BBIIHhh', client.packets[2]) == (1, 2, 123, 8, 300, 200, 0)
        assert struct.unpack('<BBIIHhh', client.packets[3]) == (1, 2, 123, 9, 300, 0, 500)
        await remote.stop()
        assert client.packets[-1] == encode_stop()
    asyncio.run(scenario())


def test_original_firmware_uses_ascii_only():
    async def scenario():
        client = Client()
        remote = Remote(client, legacy=True)
        for command in 'FBLR':
            await remote.move(command)
        await remote.stop()
        assert client.packets == [b'F', b'B', b'L', b'R', b'S']
        assert not remote.moving
    asyncio.run(scenario())


@pytest.mark.parametrize('held,enabled,expected', [
    ({'F'}, True, 'F'), (set(), True, None), ({'F', 'B'}, True, None),
    ({'L'}, False, None), ({'R'}, True, 'R'),
])
def test_release_conflict_and_focus_stop(held, enabled, expected):
    assert direction(held, enabled) == expected


def test_write_failure_propagates_without_silent_reconnect():
    async def scenario():
        client = Client()
        async def failed(*args, **kwargs):
            raise OSError('disconnected')
        client.write_gatt_char = failed
        remote = Remote(client, legacy=True)
        with pytest.raises(OSError, match='disconnected'):
            await remote.move('F')
        assert not remote.moving
    asyncio.run(scenario())
