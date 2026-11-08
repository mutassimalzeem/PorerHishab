"""Bound requests before framework parsing, including chunked uploads."""
import json
from python_multipart import MultipartParser, QuerystringParser
from python_multipart.multipart import parse_options_header

MAX_FORM_PARTS = 128
MAX_HEADER_BYTES = 8192
MAX_HEADERS = 32
MAX_FORM_FIELD_BYTES = 64 * 1024


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_bytes=5 * 1024 * 1024):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
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
        # Admit the complete bounded body before creating parser temp files.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                return await self._reject(send, 413, "Request body too large")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        try:
            self._check_form(headers.get(b"content-type", b""), body)
        except (ValueError, OverflowError):
            return await self._reject(send, 413, "Form limits exceeded")
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    def _check_form(self, content_type, body):
        if len(content_type) > 4096:
            raise ValueError("Content type too large")
        media, options = parse_options_header(content_type)
        parts = headers = header_bytes = field_bytes = 0

        def part_begin():
            nonlocal parts, headers, header_bytes, field_bytes
            parts += 1
            headers = header_bytes = field_bytes = 0
            if parts > MAX_FORM_PARTS:
                raise ValueError("Too many fields or files")

        def header_data(data, start, end):
            nonlocal header_bytes
            header_bytes += end - start
            if header_bytes > MAX_HEADER_BYTES:
                raise ValueError("Multipart headers too large")

        def header_end():
            nonlocal headers
            headers += 1
            if headers > MAX_HEADERS:
                raise ValueError("Too many multipart headers")

        def field_data(data, start, end):
            nonlocal field_bytes
            field_bytes += end - start
            if field_bytes > MAX_FORM_FIELD_BYTES:
                raise ValueError("Form field too large")

        if media == b"multipart/form-data":
            boundary = options.get(b"boundary", b"")
            if not boundary or len(boundary) > 200:
                raise ValueError("Invalid multipart boundary")
            parser = MultipartParser(boundary, {
                "on_part_begin": part_begin,
                "on_header_field": header_data,
                "on_header_value": header_data,
                "on_header_end": header_end,
            }, max_size=self.max_body_bytes)
        elif media == b"application/x-www-form-urlencoded":
            parser = QuerystringParser({
                "on_field_start": part_begin,
                "on_field_name": field_data,
                "on_field_data": field_data,
            }, max_size=self.max_body_bytes)
        else:
            return
        parser.write(body)
        parser.finalize()

    async def _reject(self, send, status, detail):
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
