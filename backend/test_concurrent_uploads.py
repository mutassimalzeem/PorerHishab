"""Operational concurrency limits and memory behavior under concurrent uploads (Issue D)."""
import asyncio
import gc
import json
import re
import tracemalloc
from pathlib import Path
import pytest
from app.middleware.request_size_limit import RequestBodyLimitMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]


async def _run_upload(middleware, payload: bytes, content_type: bytes = b"application/octet-stream"):
    messages = [{"type": "http.request", "body": payload, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": "http",
        "headers": [
            (b"content-type", content_type),
            (b"content-length", str(len(payload)).encode()),
        ],
    }
    await middleware(scope, receive, send)
    status = sent[0]["status"] if sent else 500
    return status


@pytest.mark.parametrize("multipart", [False, True])
def test_concurrent_maximum_upload_peak_traced_allocations(multipart):
    """Measure held/peak Python allocations, not RSS or post-GC retention."""
    async def check():
        size, count = 5 * 1024 * 1024, 3
        all_entered, release = asyncio.Event(), asyncio.Event()
        entered = 0
        async def inner(scope, receive, send):
            nonlocal entered
            assert len((await receive())["body"]) == size
            entered += 1
            if entered == count:
                all_entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        middleware = RequestBodyLimitMiddleware(inner, max_concurrent_requests=count)
        gc.collect()
        tracemalloc.start()
        tasks = []
        try:
            baseline, _ = tracemalloc.get_traced_memory()
            payloads = []
            for i in range(count):
                if multipart:
                    prefix = (b'--audit\r\nContent-Disposition: form-data; name="file"; '
                              b'filename="synthetic.csv"\r\nContent-Type: text/csv\r\n\r\n')
                    suffix = b"\r\n--audit--\r\n"
                    payload = prefix + bytes([65 + i]) * (size - len(prefix) - len(suffix)) + suffix
                else:
                    payload = bytes([65 + i]) * size
                payloads.append(payload)
            assert len({id(value) for value in payloads}) == count
            assert all(len(value) == size for value in payloads)
            content_type = b"multipart/form-data; boundary=audit" if multipart else b"application/octet-stream"
            tasks = [asyncio.create_task(_run_upload(middleware, value, content_type)) for value in payloads]
            await asyncio.wait_for(all_entered.wait(), 3)
            held, peak = tracemalloc.get_traced_memory()
            # All independent client payloads and replay bodies coexist here.
            assert held - baseline >= count * size
            assert peak - baseline >= 2 * count * size
            assert peak - baseline < 4 * count * size + 8 * 1024 * 1024
            assert middleware._active_requests == count
            print("TRACED_FIXTURE " + json.dumps({"multipart": multipart,
                  "independent_uploads": count, "bytes_each": size,
                  "held_bytes_above_baseline": held - baseline,
                  "peak_bytes_above_baseline": peak - baseline}, sort_keys=True))
            # Admission is saturated while the maximum-sized bodies are retained.
            assert await _run_upload(middleware, b"rejected") == 503
            release.set()
            assert await asyncio.gather(*tasks) == [204] * count
            assert middleware._active_requests == 0
        finally:
            release.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            tracemalloc.stop()
    asyncio.run(check())


@pytest.mark.parametrize("multipart", [False, True])
def test_completed_uploads_reclaim_traced_allocations(multipart):
    """Check post-cleanup traced allocations for ordinary and multipart uploads.

    The candidate 300-KiB tolerance requires runtime validation in the pinned,
    approved isolated environment. This does not establish RSS recovery or
    leak freedom.
    """
    async def check():
        count = 3
        expected_size = entered = 0
        all_entered, release = asyncio.Event(), asyncio.Event()

        async def inner(scope, receive, send):
            nonlocal entered
            message = await receive()
            assert len(message["body"]) == expected_size
            entered += 1
            if entered == count:
                all_entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            # Exercise response-buffer references as well as the admitted body.
            await send({"type": "http.response.body", "body": message["body"]})

        middleware = RequestBodyLimitMiddleware(inner, max_concurrent_requests=count)

        async def run_batch(size):
            nonlocal expected_size, entered, all_entered, release
            expected_size, entered = size, 0
            all_entered, release = asyncio.Event(), asyncio.Event()
            prefix = (b'--reclaim\r\nContent-Disposition: form-data; name="file"; '
                      b'filename="synthetic.csv"\r\nContent-Type: text/csv\r\n\r\n') if multipart else b""
            suffix = b"\r\n--reclaim--\r\n" if multipart else b""
            payloads = [
                prefix + bytes([65 + i]) * (size - len(prefix) - len(suffix)) + suffix
                for i in range(count)
            ]
            content_type = b"multipart/form-data; boundary=reclaim" if multipart else b"application/octet-stream"
            tasks = []
            try:
                tasks = [
                    asyncio.create_task(_run_upload(middleware, payload, content_type))
                    for payload in payloads
                ]
                await asyncio.wait_for(all_entered.wait(), 3)
                assert middleware._active_requests == count
                release.set()
                assert await asyncio.gather(*tasks) == [200] * count
                assert all(task.done() for task in tasks)
                assert middleware._active_requests == 0
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks.clear()
                payloads.clear()
            # Returning releases helper frames and _run_upload's response lists.

        started_tracing = not tracemalloc.is_tracing()
        if started_tracing:
            tracemalloc.start()
        try:
            # Warm the same middleware/parser/task path before taking the baseline.
            await run_batch(1024)
            await asyncio.sleep(0)
            gc.collect()
            baseline = tracemalloc.get_traced_memory()[0]
            for _ in range(3):
                await run_batch(1024 * 1024)
                await asyncio.sleep(0)
                gc.collect()
                retained = tracemalloc.get_traced_memory()[0] - baseline
                # Allow small task/parser caches, but less than one 1-MiB body.
                assert retained < 300 * 1024, (
                    f"Post-cleanup traced allocation delta {retained} bytes exceeds the candidate "
                    "300-KiB tolerance; runtime stability requires pinned isolated validation."
                )
        finally:
            if started_tracing:
                tracemalloc.stop()
    asyncio.run(check())


def test_concurrent_mixed_valid_and_oversized_uploads():
    """Verify oversized concurrent uploads are rejected with 413 without starving valid ones."""
    async def _async_test():
        async def dummy_app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = RequestBodyLimitMiddleware(dummy_app, max_body_bytes=1024 * 1024)  # 1 MiB limit

        valid_payload = b"v" * (200 * 1024)     # 200 KiB -> should pass
        oversized_payload = b"o" * (2 * 1024 * 1024)  # 2 MiB -> should get 413

        tasks = [
            _run_upload(middleware, valid_payload),
            _run_upload(middleware, oversized_payload),
            _run_upload(middleware, valid_payload),
            _run_upload(middleware, oversized_payload),
        ]
        results = await asyncio.gather(*tasks)

        assert results == [204, 413, 204, 413]

    asyncio.run(_async_test())


def test_reverse_proxy_configuration_contract():
    """Verify that deploy/nginx/proxy.conf defines strict operational limits."""
    proxy_conf = REPO_ROOT / "deploy" / "nginx" / "proxy.conf"
    assert proxy_conf.is_file(), "deploy/nginx/proxy.conf must exist"

    content = proxy_conf.read_text(encoding="utf-8")
    # Ingress body limit: 5M
    assert re.search(r"client_max_body_size\s+5M;", content)
    # Timeouts defined against Slowloris attacks
    assert re.search(r"client_body_timeout\s+\d+s;", content)
    assert re.search(r"proxy_read_timeout\s+\d+s;", content)
    assert re.search(r"proxy_connect_timeout\s+\d+s;", content)
    # Concurrency / connection limiting defined
    assert re.search(r"limit_conn_zone", content)
    assert re.search(r"limit_conn\s+\w+\s+\d+;", content)


def test_server_entrypoint_configuration_contract():
    """Source wiring only; actual server rejection is tested over loopback."""
    compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    server = (REPO_ROOT / "backend/app/server.py").read_text(encoding="utf-8")
    assert '"python", "-m", "app.server"' in compose
    assert '"python", "-m", "app.server"' in dockerfile
    assert "limit_concurrency=settings.SERVER_LIMIT_CONCURRENCY" in server
    assert "timeout_keep_alive=settings.SERVER_KEEPALIVE_SECONDS" in server
    assert "SERVER_FORWARDED_ALLOW_IPS" in compose
