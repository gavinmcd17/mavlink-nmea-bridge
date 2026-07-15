"""Non-blocking NMEA TCP broadcaster."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable

LOG = logging.getLogger(__name__)


class NMEAServer:
    """Broadcast periodically generated NMEA payloads to all TCP clients."""

    def __init__(self, host: str, port: int, interval: float, payload: Callable[[], bytes]) -> None:
        self.host, self.port, self.interval, self.payload = host, port, interval, payload
        self._writers: set[asyncio.StreamWriter] = set()
        self._server: asyncio.AbstractServer | None = None
        self._stop = asyncio.Event()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        del reader
        self._writers.add(writer)
        peer = writer.get_extra_info("peername")
        sock = writer.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        LOG.info("TCP client connected: %s", peer)
        try:
            await self._stop.wait()
        finally:
            self._writers.discard(writer)
            writer.close()
            await writer.wait_closed()
            LOG.info("TCP client disconnected: %s", peer)

    async def run(self) -> None:
        """Serve clients and broadcast payloads until shutdown is requested."""

        try:
            self._server = await asyncio.start_server(self._client, self.host, self.port, reuse_address=True)
            LOG.info("NMEA TCP listening on %s:%s", self.host, self.port)
            while not self._stop.is_set():
                await asyncio.sleep(self.interval)
                payload = self.payload()
                dead: list[asyncio.StreamWriter] = []
                for writer in tuple(self._writers):
                    try:
                        writer.write(payload)
                        await asyncio.wait_for(writer.drain(), timeout=min(1.0, self.interval))
                    except (ConnectionError, OSError, asyncio.TimeoutError):
                        dead.append(writer)
                for writer in dead:
                    self._writers.discard(writer)
                    writer.close()
        finally:
            self._stop.set()
            if self._server:
                self._server.close()
                await self._server.wait_closed()
            for writer in tuple(self._writers):
                writer.close()
            if self._writers:
                await asyncio.gather(*(w.wait_closed() for w in self._writers), return_exceptions=True)
            self._writers.clear()

    def stop(self) -> None:
        """Request server shutdown."""

        self._stop.set()
