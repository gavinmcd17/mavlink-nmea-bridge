import asyncio
import socket
from mavlink_nmea_bridge.tcp_server import NMEAServer

def test_tcp_client_disconnect_reconnect_and_multiple_clients():
    async def exercise() -> None:
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
        server = NMEAServer("127.0.0.1", port, 0.01, lambda: b"$TEST\r\n")
        task = asyncio.create_task(server.run())
        await asyncio.sleep(0.02)
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        assert await r1.readline() == b"$TEST\r\n"
        assert await r2.readline() == b"$TEST\r\n"
        w1.close(); await w1.wait_closed()
        r3, w3 = await asyncio.open_connection("127.0.0.1", port)
        assert await r3.readline() == b"$TEST\r\n"
        w2.close(); w3.close(); await w2.wait_closed(); await w3.wait_closed()
        server.stop(); await asyncio.wait_for(task, 1)
    asyncio.run(exercise())
