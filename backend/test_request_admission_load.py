"""Disposable loopback Uvicorn/RSS checks. Run only under OS resource/network isolation.

The child serves a synthetic ASGI fixture, never app.main or financial endpoints.
Control routes exist only in this fixture, inside the isolated loopback namespace.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest
import uvicorn
from app.middleware.request_size_limit import RequestBodyLimitMiddleware

pytestmark = pytest.mark.skipif(
    os.environ.get("AI18C2_RUN_ISOLATED_LOAD_TESTS") != "1",
    reason="Opt in only inside an OS-isolated loopback/resource-limited environment",
)

SIZE = 5 * 1024 * 1024


def _serve(port):
    import resource
    release = asyncio.Event()
    held = 0
    async def respond(send, value):
        body = json.dumps(value).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
    async def inner(scope, receive, send):
        nonlocal held
        message = await receive()
        assert len(message["body"]) == SIZE
        held += 1
        try:
            await asyncio.wait_for(release.wait(), 10)
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        finally:
            held -= 1
    admission = RequestBodyLimitMiddleware(inner, max_concurrent_requests=3, body_timeout_seconds=2)
    async def fixture(scope, receive, send):
        if scope["path"] == "/control/state":
            return await respond(send, {"held": held, "rss_high_water_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        if scope["path"] == "/control/release":
            release.set()
            return await respond(send, {"released": True})
        return await admission(scope, receive, send)
    uvicorn.run(fixture, host="127.0.0.1", port=port, lifespan="off", log_level="critical",
                proxy_headers=False, limit_concurrency=8, timeout_keep_alive=1)


async def _close(writer):
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


async def _json_get(port, path):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), 3)
        assert data.startswith(b"HTTP/1.1 200")
        return json.loads(data.split(b"\r\n\r\n", 1)[1])
    finally:
        await _close(writer)


async def _upload(port, payload):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(f"POST /upload HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(payload)}\r\nExpect: 100-continue\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
        status = int(headers.split()[1])
        if status == 100:
            writer.write(payload)
            await writer.drain()
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            status = int(headers.split()[1])
        return status
    finally:
        await _close(writer)


def _rss_kib(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise AssertionError("Linux RSS metric unavailable")


@pytest.mark.skipif(sys.platform != "linux", reason="Requires isolated Linux /proc RSS observation")
def test_separate_uvicorn_process_rss_and_admission():
    async def check():
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--load-server", str(port)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        samples, uploads = [], []
        async def sample():
            while True:
                samples.append(_rss_kib(child.pid))
                await asyncio.sleep(0.005)
        sampler = None
        try:
            deadline = time.monotonic() + 5
            while True:
                if child.poll() is not None:
                    raise AssertionError("Synthetic Uvicorn child failed to start")
                try:
                    initial = await _json_get(port, "/control/state")
                    break
                except OSError:
                    assert time.monotonic() < deadline
                    await asyncio.sleep(0.02)
            baseline = _rss_kib(child.pid)
            sampler = asyncio.create_task(sample())
            payloads = [bytes([65 + i]) * SIZE for i in range(3)]
            assert len({id(value) for value in payloads}) == 3
            uploads = [asyncio.create_task(_upload(port, payload)) for payload in payloads]
            deadline = time.monotonic() + 5
            while (await _json_get(port, "/control/state"))["held"] < 3:
                assert time.monotonic() < deadline
                await asyncio.sleep(0.01)
            samples.append(_rss_kib(child.pid))
            assert await _upload(port, b"not-admitted") == 503
            await _json_get(port, "/control/release")
            assert await asyncio.gather(*uploads) == [204] * 3
            final = await _json_get(port, "/control/state")
            peak = max(samples)
            high_water = final["rss_high_water_kib"]
            assert peak - baseline >= 3 * SIZE // 1024
            # A fixture regression ceiling, not a production capacity claim.
            assert peak - baseline < (3 * SIZE * 8 + 64 * 1024 * 1024) // 1024
            assert high_water >= initial["rss_high_water_kib"]
            print("RSS_FIXTURE " + json.dumps({"baseline_kib": baseline, "sampled_peak_kib": peak,
                  "process_high_water_kib": high_water,
                  "initial_process_high_water_kib": initial["rss_high_water_kib"],
                  "independent_maximum_uploads": 3,
                  "rejected_when_full": 1}, sort_keys=True))
        finally:
            if sampler:
                sampler.cancel()
                await asyncio.gather(sampler, return_exceptions=True)
            for task in uploads:
                if not task.done():
                    task.cancel()
            if uploads:
                await asyncio.gather(*uploads, return_exceptions=True)
            child.terminate()
            try:
                child.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=3)
    asyncio.run(check())


@pytest.mark.parametrize("mode", ["stalled", "trickle", "uvicorn-capacity"])
def test_real_uvicorn_slow_bodies_and_capacity(mode):
    async def check():
        reached = []
        async def inner(scope, receive, send):
            reached.append(True)
        middleware = RequestBodyLimitMiddleware(inner, max_concurrent_requests=8,
                         body_timeout_seconds=2 if mode == "uvicorn-capacity" else 0.12)
        server = uvicorn.Server(uvicorn.Config(middleware, host="127.0.0.1", port=0,
                    lifespan="off", log_level="critical", limit_concurrency=3,
                    proxy_headers=False, timeout_keep_alive=1))
        serving = asyncio.create_task(server.serve())
        clients, trickles = [], []
        async def partial():
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            clients.append(writer)
            writer.write(b"POST /upload HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1000\r\nConnection: close\r\n\r\nx")
            await writer.drain()
            return reader, writer
        try:
            deadline = time.monotonic() + 3
            while not server.started:
                assert time.monotonic() < deadline
                await asyncio.sleep(0.005)
            port = server.servers[0].sockets[0].getsockname()[1]
            reader, writer = await partial()
            if mode == "uvicorn-capacity":
                while middleware._active_requests < 1:
                    await asyncio.sleep(0)
                await partial()
                while middleware._active_requests < 2:
                    await asyncio.sleep(0)
                overflow_reader, _ = await partial()
                response = await asyncio.wait_for(overflow_reader.read(), 2)
                assert response.startswith(b"HTTP/1.1 503")
                assert middleware._active_requests == 2  # Uvicorn rejected before app admission.
            else:
                async def trickle():
                    try:
                        while True:
                            await asyncio.sleep(0.02)
                            writer.write(b"x")
                            await writer.drain()
                    except OSError:
                        pass
                if mode == "trickle":
                    trickles.append(asyncio.create_task(trickle()))
                response = await asyncio.wait_for(reader.read(), 2)
                assert response.startswith(b"HTTP/1.1 408")
                assert middleware._active_requests == 0
            assert reached == []
        finally:
            for task in trickles:
                task.cancel()
            if trickles:
                await asyncio.gather(*trickles, return_exceptions=True)
            for writer in clients:
                await _close(writer)
            server.should_exit = True
            await asyncio.wait_for(serving, 4)
            assert middleware._active_requests == 0
    asyncio.run(check())


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--load-server":
    _serve(int(sys.argv[2]))


@pytest.mark.parametrize("peer,trusted", [("192.0.2.10", True), ("198.51.100.20", False)])
def test_uvicorn_only_accepts_forwarded_headers_from_explicit_peer(peer, trusted):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    async def check():
        observed = []
        async def inner(scope, receive, send):
            observed.append((scope["client"][0], scope["scheme"]))
        async def unused(*args):
            raise AssertionError("No body/network processing expected")
        scope = {"type": "http", "scheme": "http", "client": (peer, 1234),
                 "headers": [(b"x-forwarded-for", b"203.0.113.7"), (b"x-forwarded-proto", b"https")]}
        await ProxyHeadersMiddleware(inner, trusted_hosts="192.0.2.10")(scope, unused, unused)
        assert observed == [("203.0.113.7", "https") if trusted else (peer, "http")]
    asyncio.run(check())
