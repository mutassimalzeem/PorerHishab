"""Operational concurrency limits and memory behavior under concurrent uploads (Issue D)."""
import asyncio
import gc
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


def test_concurrent_uploads_memory_bounded_and_reclaimed():
    """Verify that multiple concurrent uploads scale predictably and reclaim memory."""
    forwarded = []

    async def _async_test():
        async def dummy_app(scope, receive, send):
            msg = await receive()
            forwarded.append(len(msg.get("body", b"")))
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        # 5 MiB middleware cap
        middleware = RequestBodyLimitMiddleware(dummy_app, max_body_bytes=5 * 1024 * 1024)

        concurrency = 8
        payload_size = 512 * 1024  # 512 KiB per request (~4 MiB total payload)

        tracemalloc.start()
        gc.collect()
        start_cur, _ = tracemalloc.get_traced_memory()

        tasks = [
            _run_upload(middleware, b"m" * payload_size)
            for _ in range(concurrency)
        ]
        results = await asyncio.gather(*tasks)
        mid_cur, mid_peak = tracemalloc.get_traced_memory()

        # Verify all concurrent requests succeeded
        assert len(results) == concurrency
        assert all(status == 204 for status in results)
        assert len(forwarded) == concurrency

        # Peak memory must not wildly exceed expected buffered bounds
        # (payloads + Python object/asyncio overhead < 20 MiB for 4 MiB payload)
        assert mid_peak - start_cur < 20 * 1024 * 1024

        # Allow buffers to be freed
        forwarded.clear()
        gc.collect()
        end_cur, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Verify no persistent buffering leak (reclaimed within 300 KiB)
        assert end_cur - start_cur < 300 * 1024

    asyncio.run(_async_test())


def test_concurrent_multipart_uploads_memory_bounded():
    """Verify concurrent multipart form-data requests with files remain bounded."""
    async def _async_test():
        async def dummy_app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = RequestBodyLimitMiddleware(dummy_app, max_body_bytes=5 * 1024 * 1024)

        file_bytes = b"date,amount,desc\n" + b"2026-11-01,25.50,Groceries\n" * 5000  # ~140 KiB
        multipart_body = (
            b"--boundary123\r\n"
            b'Content-Disposition: form-data; name="file"; filename="tx.csv"\r\n'
            b"Content-Type: text/csv\r\n\r\n"
            + file_bytes
            + b"\r\n--boundary123--\r\n"
        )

        tracemalloc.start()
        gc.collect()
        start_cur, _ = tracemalloc.get_traced_memory()

        tasks = [
            _run_upload(middleware, multipart_body, b"multipart/form-data; boundary=boundary123")
            for _ in range(6)
        ]
        results = await asyncio.gather(*tasks)
        gc.collect()
        end_cur, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert all(status == 204 for status in results)
        assert end_cur - start_cur < 300 * 1024

    asyncio.run(_async_test())


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


def test_server_operational_limits():
    """Verify that docker-compose.prod.yml and backend/Dockerfile enforce uvicorn concurrency limits."""
    compose_prod = REPO_ROOT / "docker-compose.prod.yml"
    dockerfile = REPO_ROOT / "backend" / "Dockerfile"

    assert compose_prod.is_file()
    assert dockerfile.is_file()

    compose_text = compose_prod.read_text(encoding="utf-8")
    assert "--limit-concurrency" in compose_text
    assert "--timeout-keep-alive" in compose_text

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    assert "--limit-concurrency" in dockerfile_text
    assert "--timeout-keep-alive" in dockerfile_text
