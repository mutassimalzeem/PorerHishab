"""Bounded ASGI fixtures: no server, disk spool, or external traffic."""
import asyncio
import pytest
from app.middleware.request_size_limit import RequestBodyLimitMiddleware


def invoke(chunks, content_type=b"application/json", limit=1024, declared=None):
    forwarded, sent = [], []
    messages = [{"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1} for i, chunk in enumerate(chunks)]
    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}
    async def send(message):
        sent.append(message)
    async def inner(scope, receive, send):
        forwarded.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    headers = [(b"content-type", content_type)]
    if declared is not None:
        headers.append((b"content-length", declared))
    asyncio.run(RequestBodyLimitMiddleware(inner, max_body_bytes=limit)(
        {"type": "http", "headers": headers}, receive, send))
    return sent[0]["status"], forwarded


def test_chunked_overflow_rejected_before_parser():
    status, forwarded = invoke([b"x" * 600, b"x" * 600])
    assert status == 413 and forwarded == []


def test_declared_length_cannot_hide_real_overflow():
    assert invoke([b"x" * 1025], declared=b"1") == (413, [])


def test_exact_boundary_is_replayed_once():
    assert invoke([b"x" * 512, b"x" * 512]) == (204, [b"x" * 1024])


@pytest.mark.parametrize("body", [b"&".join([b"x=1"] * 129), b"x=" + b"a" * 65537], ids=["many-fields", "large-field"])
def test_urlencoded_limits(body):
    assert invoke([body], b"application/x-www-form-urlencoded", limit=100000)[0] == 413


def test_multipart_header_budget():
    body = b"--audit\r\nX-Test: " + b"a" * 8193 + b"\r\n\r\nx\r\n--audit--\r\n"
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=100000) == (413, [])


def test_rejected_upload_never_creates_framework_tempfile(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected upload must not reach spooling")
    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", forbidden)
    assert invoke([b"x" * 600, b"x" * 600], b"multipart/form-data; boundary=audit") == (413, [])


def test_multipart_oversized_text_field_rejected():
    # Individual form field exceeds MAX_FORM_FIELD_BYTES (64 KiB), even though body < limit (200 KiB)
    body = (
        b"--audit\r\n"
        b'Content-Disposition: form-data; name="comment"\r\n\r\n'
        + b"a" * (65 * 1024)
        + b"\r\n--audit--\r\n"
    )
    status, forwarded = invoke([body], b"multipart/form-data; boundary=audit", limit=200000)
    assert status == 413 and forwarded == []


def test_multipart_file_exceeding_field_limit_allowed_under_body_limit():
    # File parts with filename are permitted beyond 64 KiB up to max_body_bytes
    file_content = b"date,amount\n" + b"2026-11-01,10.0\n" * 5000  # ~95 KiB
    body = (
        b"--audit\r\n"
        b'Content-Disposition: form-data; name="file"; filename="tx.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n"
        + file_content
        + b"\r\n--audit--\r\n"
    )
    status, forwarded = invoke([body], b"multipart/form-data; boundary=audit", limit=200000)
    assert status == 204 and forwarded == [body]


def test_multipart_excessive_parts_rejected():
    # More than MAX_FORM_PARTS (128)
    parts = [b'--audit\r\nContent-Disposition: form-data; name="p' + str(i).encode() + b'"\r\n\r\n1\r\n' for i in range(129)]
    body = b"".join(parts) + b"--audit--\r\n"
    status, forwarded = invoke([body], b"multipart/form-data; boundary=audit", limit=200000)
    assert status == 413 and forwarded == []


def test_multipart_excessive_headers_rejected():
    # More than MAX_HEADERS (32) in a single part
    headers = [b"X-Test-Header-" + str(i).encode() + b": value\r\n" for i in range(33)]
    body = b"--audit\r\n" + b"".join(headers) + b"\r\ncontent\r\n--audit--\r\n"
    status, forwarded = invoke([body], b"multipart/form-data; boundary=audit", limit=200000)
    assert status == 413 and forwarded == []
