"""Admit bounded bodies before framework parsing or temporary-file spooling."""
import asyncio
import json
import math
import re
from threading import Lock
from python_multipart import MultipartParser, QuerystringParser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header

MAX_FORM_PARTS = 128
MAX_HEADER_BYTES = 8192
# Preserve python-multipart 0.0.33's stricter existing eight-header ceiling.
MAX_HEADERS = 8
MAX_FORM_FIELD_BYTES = 64 * 1024
_BOUNDARY = re.compile(rb"[0-9A-Za-z'()+_,./:=? -]{1,70}")


class _BodyTooLarge(ValueError):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_bytes=5 * 1024 * 1024,
                 max_concurrent_requests=16, body_timeout_seconds=15):
        if (not 1 <= max_concurrent_requests <= 256 or max_body_bytes <= 0
                or not math.isfinite(body_timeout_seconds) or body_timeout_seconds <= 0):
            raise ValueError("Invalid request admission limits")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_concurrent_requests = max_concurrent_requests
        self.body_timeout_seconds = body_timeout_seconds
        self._active_requests = 0
        self._admission_lock = Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # No waiters or body allocations for excess requests. The short lock also
        # protects instances called from multiple threads/event loops in tests.
        with self._admission_lock:
            admitted = self._active_requests < self.max_concurrent_requests
            if admitted:
                self._active_requests += 1
        if not admitted:
            return await self._reject(send, 503, "Request capacity exceeded")
        try:
            await self._admit(scope, receive, send)
        finally:
            with self._admission_lock:
                self._active_requests -= 1

    async def _read_body(self, receive):
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                raise _BodyTooLarge
            body.extend(chunk)
            if not message.get("more_body", False):
                return body

    async def _admit(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                size = int(declared)
                if size < 0:
                    raise ValueError
            except ValueError:
                return await self._reject(send, 400, "Invalid Content-Length")
            if size > self.max_body_bytes:
                return await self._reject(send, 413, "Request body too large")
        try:
            # One deadline for the complete body; sending occasional chunks does
            # not extend it. Uvicorn keep-alive only bounds idle connections.
            body = await asyncio.wait_for(self._read_body(receive), self.body_timeout_seconds)
        except asyncio.TimeoutError:
            return await self._reject(send, 408, "Request body timeout")
        except _BodyTooLarge:
            return await self._reject(send, 413, "Request body too large")
        if body is None:
            return
        try:
            self._check_form(headers.get(b"content-type", b""), body)
        except FormParserError:
            # 0.0.33: MultipartParseError -> ParseError -> FormParserError -> ValueError.
            # Keep parser failures explicit; do not catch unrelated programming errors.
            return await self._reject(send, 413, "Malformed form data")
        except (ValueError, OverflowError):
            return await self._reject(send, 413, "Form limits exceeded")
        payload = bytes(body)
        del body
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        # Hold admission until downstream completes: parsers and responses can
        # retain a copy of the body after receive(), so releasing earlier is unsafe.
        await self.app(scope, replay, send)

    def _check_form(self, content_type, body):
        if len(content_type) > 4096:
            raise ValueError("Content type too large")
        media, options = parse_options_header(content_type)
        parts = headers = header_bytes = field_bytes = 0
        is_file = disposition_seen = ended = False
        header_start = None
        current_header_name = bytearray()
        current_header_value = bytearray()

        def part_begin():
            nonlocal parts, headers, header_bytes, field_bytes, is_file, disposition_seen, header_start
            parts += 1
            headers = header_bytes = field_bytes = 0
            is_file = disposition_seen = False
            header_start = None
            current_header_name.clear()
            current_header_value.clear()
            if parts > MAX_FORM_PARTS:
                raise ValueError("Too many fields or files")

        def header_field(data, start, end):
            nonlocal header_bytes, header_start
            if header_start is None:
                # The admitted body is passed to parser.write() exactly once, so
                # callback offsets refer to this whole buffer. Bound the raw
                # header lines too: callbacks omit whitespace after a colon.
                header_start = start
                terminal = body.find(b"\r\n\r\n", start, start + MAX_HEADER_BYTES + 2)
                if terminal < 0 or terminal + 2 - start > MAX_HEADER_BYTES:
                    raise ValueError("Multipart headers too large")
            header_bytes += end - start
            if header_bytes > MAX_HEADER_BYTES:
                raise ValueError("Multipart headers too large")
            current_header_name.extend(data[start:end])

        def header_value(data, start, end):
            nonlocal header_bytes
            header_bytes += end - start
            if header_bytes > MAX_HEADER_BYTES:
                raise ValueError("Multipart headers too large")
            current_header_value.extend(data[start:end])

        def header_end():
            nonlocal headers, header_bytes, is_file, disposition_seen
            headers += 1
            header_bytes += 4  # colon, space and CRLF in addition to name/value
            if headers > MAX_HEADERS or header_bytes > MAX_HEADER_BYTES:
                raise ValueError("Multipart header limits exceeded")
            if current_header_name.lower() == b"content-disposition":
                if disposition_seen:
                    raise ValueError("Duplicate multipart disposition")
                disposition_seen = True
                disposition, parameters = parse_options_header(bytes(current_header_value))
                if disposition != b"form-data" or b"name" not in parameters:
                    raise ValueError("Invalid multipart disposition")
                # Match Starlette's parsed filename semantics, not a substring.
                is_file = b"filename" in parameters
            current_header_name.clear()
            current_header_value.clear()

        def headers_finished():
            if not disposition_seen:
                raise ValueError("Missing multipart disposition")

        def multipart_field_data(data, start, end):
            nonlocal field_bytes
            if not is_file:
                field_bytes += end - start
                if field_bytes > MAX_FORM_FIELD_BYTES:
                    raise ValueError("Form field too large")

        def urlencoded_field_data(data, start, end):
            nonlocal field_bytes
            field_bytes += end - start
            if field_bytes > MAX_FORM_FIELD_BYTES:
                raise ValueError("Form field too large")

        def end():
            nonlocal ended
            ended = True

        multipart = media == b"multipart/form-data"
        if multipart:
            boundary = options.get(b"boundary", b"")
            if not _BOUNDARY.fullmatch(boundary) or boundary.endswith(b" "):
                raise ValueError("Invalid multipart boundary")
            if not body.startswith(b"--" + boundary):
                raise ValueError("Invalid multipart body")
            parser = MultipartParser(boundary, {
                "on_part_begin": part_begin,
                "on_header_field": header_field,
                "on_header_value": header_value,
                "on_header_end": header_end,
                "on_headers_finished": headers_finished,
                "on_part_data": multipart_field_data,
                "on_end": end,
            }, max_size=self.max_body_bytes)
        elif media == b"application/x-www-form-urlencoded":
            parser = QuerystringParser({
                "on_field_start": part_begin,
                "on_field_name": urlencoded_field_data,
                "on_field_data": urlencoded_field_data,
            }, max_size=self.max_body_bytes)
        else:
            return
        parser.write(body)
        parser.finalize()
        # MultipartParser.finalize() does not validate completion. Only on_end
        # proves a terminal boundary was parsed, before Starlette can spool files.
        if multipart and not ended:
            raise ValueError("Incomplete multipart body")

    async def _reject(self, send, status, detail):
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
