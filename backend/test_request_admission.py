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


def multipart_body(value=b"ok", filename=None, extra_headers=b""):
    disposition = b'Content-Disposition: form-data; name="file"'
    if filename is not None:
        disposition += b'; filename="' + filename + b'"'
    return b"--audit\r\n" + disposition + b"\r\n" + extra_headers + b"\r\n" + value + b"\r\n--audit--\r\n"


@pytest.mark.parametrize("size,expected", [(65535, 204), (65536, 204), (65537, 413)])
def test_multipart_text_field_exact_boundary(size, expected):
    body = multipart_body(b"a" * size)
    status, forwarded = invoke([body[:90], body[90:]], b"multipart/form-data; boundary=audit", limit=200000)
    assert status == expected
    assert bool(forwarded) == (expected == 204)


@pytest.mark.parametrize("count,expected", [(128, 204), (129, 413)])
def test_multipart_part_boundary(count, expected):
    part = b'--audit\r\nContent-Disposition: form-data; name="x"\r\n\r\n1\r\n'
    body = part * count + b"--audit--\r\n"
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000)[0] == expected


@pytest.mark.parametrize("extra_count,expected", [(7, 204), (8, 413)])
def test_multipart_header_count_boundary(extra_count, expected):
    body = multipart_body(extra_headers=b"X-Test: value\r\n" * extra_count)
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000)[0] == expected


@pytest.mark.parametrize("content_type", [
    b"multipart/form-data", b"multipart/form-data; boundary=",
    b"multipart/form-data; boundary=" + b"a" * 71,
    b'multipart/form-data; boundary="audit "',
    b'multipart/form-data; boundary="audit\r\nx"',
])
def test_invalid_multipart_boundary_never_forwarded(content_type):
    assert invoke([multipart_body()], content_type, limit=200000) == (413, [])


@pytest.mark.parametrize("body", [
    b"", b"garbage", b"--wrong--\r\n", b"--audit\r\n",
    b'--audit\r\nContent-Disposition: form-data; name="x"\r\n\r\nunfinished',
    b'--audit\r\nBad header\r\n\r\nx\r\n--audit--\r\n',
    b'--audit\r\nX-Test: value\r\n\r\nx\r\n--audit--\r\n',
    b'--audit\r\nContent-Disposition: form-data\r\n\r\nx\r\n--audit--\r\n',
    b'--audit\r\nContent-Disposition: form-data; name="x"\r\nContent-Disposition: form-data; name="y"\r\n\r\nx\r\n--audit--\r\n',
])
def test_malformed_multipart_rejected_before_framework(body, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected upload reached framework parser or spooling")
    monkeypatch.setattr("starlette.formparsers.MultiPartParser.parse", forbidden)
    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", forbidden)
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000) == (413, [])


def test_filename_substring_cannot_bypass_text_limit():
    body = multipart_body(b"a" * 65537).replace(b'name="file"', b'name="filename=decoy"')
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000) == (413, [])


def test_valid_csv_is_parsed_after_admission():
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Route
    body = multipart_body(b"date,amount\n2026-01-01,10\n", filename=b"synthetic.csv",
                          extra_headers=b"Content-Type: text/csv\r\n")
    async def upload(request: Request):
        async with request.form() as form:
            assert form["file"].filename == "synthetic.csv"
            assert await form["file"].read() == b"date,amount\n2026-01-01,10\n"
        return Response(status_code=204)
    async def check():
        sent = []
        messages = [{"type": "http.request", "body": body, "more_body": False}]
        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}
        async def send(message):
            sent.append(message)
        application = RequestBodyLimitMiddleware(Starlette(routes=[Route("/upload", upload, methods=["POST"])]))
        await application({"type": "http", "method": "POST", "path": "/upload", "query_string": b"",
                           "headers": [(b"content-type", b"multipart/form-data; boundary=audit")]}, receive, send)
        assert sent[0]["status"] == 204
    asyncio.run(check())


def test_default_five_mib_limit_without_content_length():
    async def check():
        reached, sent = [], []
        async def inner(*args):
            reached.append(True)
        messages = [
            {"type": "http.request", "body": b"x" * (5 * 1024 * 1024), "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": False},
        ]
        async def receive():
            return messages.pop(0)
        async def send(message):
            sent.append(message)
        await RequestBodyLimitMiddleware(inner)({"type": "http"}, receive, send)
        assert sent[0]["status"] == 413 and reached == []
    asyncio.run(check())


def test_concurrent_uploads_reject_without_reading_or_queueing():
    async def check():
        entered = asyncio.Event()
        release = asyncio.Event()
        read_count = active = peak = 0
        payload = b"x" * (5 * 1024 * 1024)
        responses = []
        async def inner(scope, receive, send):
            nonlocal active, peak
            assert (await receive())["body"] == payload
            active += 1
            peak = max(peak, active)
            if active == 2:
                entered.set()
            await release.wait()
            active -= 1
            await send({"type": "http.response.start", "status": 204})
        async def receive():
            nonlocal read_count
            read_count += 1
            return {"type": "http.request", "body": payload, "more_body": False}
        async def send(message):
            if message["type"] == "http.response.start":
                responses.append(message["status"])
        middleware = RequestBodyLimitMiddleware(inner, max_concurrent_requests=2)
        tasks = [asyncio.create_task(middleware({"type": "http"}, receive, send)) for _ in range(2)]
        await asyncio.wait_for(entered.wait(), 2)
        # Additional uploads are rejected before receive() is called, even while
        # admitted handlers retain full bodies. No semaphore waiters accumulate.
        await asyncio.wait_for(asyncio.gather(*[
            middleware({"type": "http"}, receive, send) for _ in range(30)
        ]), 2)
        assert read_count == peak == 2
        assert responses == [503] * 30
        assert middleware._active_requests == 2
        release.set()
        await asyncio.gather(*tasks)
        assert middleware._active_requests == 0
        await middleware({"type": "http"}, receive, send)
        assert responses[-1] == 204
    asyncio.run(check())


@pytest.mark.parametrize("mode", ["disconnect", "exception", "cancel", "timeout"])
def test_admission_slots_released_on_every_exit(mode):
    async def check():
        started = asyncio.Event()
        reached = []
        sent = []
        async def receive():
            started.set()
            if mode == "disconnect":
                return {"type": "http.disconnect"}
            if mode == "exception":
                raise RuntimeError("synthetic receive failure")
            await asyncio.Event().wait()
        async def inner(*args):
            reached.append(True)
        async def send(message):
            sent.append(message)
        middleware = RequestBodyLimitMiddleware(inner, max_concurrent_requests=1, body_timeout_seconds=0.03)
        task = asyncio.create_task(middleware({"type": "http"}, receive, send))
        await started.wait()
        if mode == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode == "exception":
            with pytest.raises(RuntimeError):
                await task
        else:
            await task
        assert middleware._active_requests == 0
        assert reached == []
        if mode == "timeout":
            assert sent[0]["status"] == 408
    asyncio.run(check())


def test_body_deadline_is_not_extended_by_trickle_chunks():
    async def check():
        sent = []
        async def receive():
            await asyncio.sleep(0.01)
            return {"type": "http.request", "body": b"x", "more_body": True}
        async def inner(*args):
            raise AssertionError("Timed-out body must not reach framework")
        async def send(message):
            sent.append(message)
        middleware = RequestBodyLimitMiddleware(inner, body_timeout_seconds=0.04)
        await asyncio.wait_for(middleware({"type": "http"}, receive, send), 1)
        assert sent[0]["status"] == 408
    asyncio.run(check())


@pytest.mark.parametrize("total,expected", [(8191, 204), (8192, 204), (8193, 413)])
def test_cumulative_multipart_header_byte_boundary(total, expected):
    disposition = b'Content-Disposition: form-data; name="file"\r\n'
    # Each line stays below the parser's own 4224-byte single-line cap.
    second_size = total - len(disposition) - 4000 - len(b"X-A: \r\nX-B: \r\n")
    extra = b"X-A: " + b"a" * 4000 + b"\r\nX-B: " + b"b" * second_size + b"\r\n"
    body = multipart_body(extra_headers=extra)
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000)[0] == expected



def test_header_padding_counts_toward_aggregate_byte_limit():
    # Every line is below 4224 bytes and the count is below eight, but omitted
    # leading value whitespace must still count toward the 8192-byte total.
    extra = b"X-Padding:" + b" " * 3000 + b"x\r\n"
    body = multipart_body(extra_headers=extra * 3)
    assert invoke([body], b"multipart/form-data; boundary=audit", limit=200000) == (413, [])



def test_pinned_multipart_exception_hierarchy_and_controlled_rejection(monkeypatch):
    from python_multipart.exceptions import FormParserError, MultipartParseError, ParseError
    assert MultipartParseError.__mro__[:4] == (MultipartParseError, ParseError, FormParserError, ValueError)
    def malformed(*args, **kwargs):
        raise MultipartParseError("synthetic malformed input")
    monkeypatch.setattr(RequestBodyLimitMiddleware, "_check_form", malformed)
    assert invoke([b"malformed"], b"multipart/form-data; boundary=audit") == (413, [])


def test_unexpected_parser_bug_is_not_swallowed(monkeypatch):
    def bug(*args, **kwargs):
        raise RuntimeError("synthetic programming error")
    monkeypatch.setattr(RequestBodyLimitMiddleware, "_check_form", bug)
    with pytest.raises(RuntimeError):
        invoke([b"malformed"])


@pytest.mark.parametrize("body", [
    b'--audit\r\nContent-Disposition: form-data; name="x"',
    b'--audit\r\nContent-Disposition:',
    b'--audit\r\nContent-Disposition: attachment; name="x"\r\n\r\nx\r\n--audit--\r\n',
])
def test_truncated_headers_and_malformed_disposition_are_controlled(body, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected request reached parser/spool")
    monkeypatch.setattr("starlette.formparsers.MultiPartParser.parse", forbidden)
    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", forbidden)
    assert invoke([body], b"multipart/form-data; boundary=audit") == (413, [])
