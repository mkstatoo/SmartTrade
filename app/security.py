"""Request hardening: failed-auth throttle and a streaming request-body size limit."""
import threading
import time
from collections import defaultdict, deque


class AuthThrottle:
    """Per-client sliding window of FAILED authentications. While a client is over the limit every request from it is
    refused (429), whatever key it sends. State is per process; with several workers the effective limit is per worker."""

    def __init__(self, limit: int, window_sec: int, now=time.monotonic):
        self.limit, self.window, self._now = limit, window_sec, now
        self._fails = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, q, t):
        while q and q[0] <= t - self.window:
            q.popleft()

    def retry_after(self, client: str) -> int:
        """Seconds until the client may try again (0 = allowed now)."""
        with self._lock:
            t = self._now()
            q = self._fails[client]
            self._trim(q, t)
            if len(q) < self.limit:
                return 0
            return max(1, int(q[0] + self.window - t) + 1)

    def failure(self, client: str) -> None:
        with self._lock:
            t = self._now()
            q = self._fails[client]
            self._trim(q, t)
            q.append(t)
            if len(self._fails) > 10_000:                      # bound memory under an address-spraying attack
                for k in [k for k, v in self._fails.items() if not v or v[-1] <= t - self.window][:5_000]:
                    self._fails.pop(k, None)

    def success(self, client: str) -> None:
        with self._lock:
            self._fails.pop(client, None)


class BodyLimitMiddleware:
    """Pure ASGI middleware: refuse bodies larger than `limit` bytes with 413, also when they are chunked."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    if int(v) > self.limit:
                        return await self._reject(send)
                except ValueError:
                    return await self._reject(send, 400)
        seen = 0
        exceeded = False
        started = False
        replaced = False

        async def limited_receive():
            nonlocal seen, exceeded
            if exceeded:
                return {"type": "http.request", "body": b"", "more_body": False}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.limit:
                    exceeded = True                           # stop feeding the app; answer 413 ourselves
                    return {"type": "http.request", "body": b"", "more_body": False}
            return msg

        async def tracking_send(msg):
            nonlocal started, replaced
            if exceeded and not started:
                if not replaced:
                    replaced = True
                    await self._reject(send)
                return                                        # swallow whatever the app answered
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        await self.app(scope, limited_receive, tracking_send)

    @staticmethod
    async def _reject(send, status=413):
        body = b'{"detail":"request body too large"}' if status == 413 else b'{"detail":"bad content-length"}'
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

