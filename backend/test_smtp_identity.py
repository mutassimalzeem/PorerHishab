"""One bounded loopback SMTP peer; only synthetic credentials and certificates."""
import socket
import ssl
from datetime import datetime, timedelta, timezone
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.notifications.email_sender import EmailMessage, SmtpEmailSender


def test_untrusted_smtp_certificate_is_rejected_before_auth(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "untrusted.example")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(hours=1))
            .sign(key, hashes.SHA256()))
    keyfile, certfile = tmp_path / "dummy-key.pem", tmp_path / "dummy-cert.pem"
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    seen = {"starttls": False, "auth": False, "tls_aborted": False}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(3)
    port = listener.getsockname()[1]

    def peer():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(2)
                conn.sendall(b"220 audit ESMTP\r\n")
                with conn.makefile("rb") as stream:
                    assert stream.readline().upper().startswith(b"EHLO")
                    conn.sendall(b"250-audit\r\n250 STARTTLS\r\n")
                    seen["starttls"] = stream.readline().upper().startswith(b"STARTTLS")
                    conn.sendall(b"220 Ready\r\n")
                try:
                    with context.wrap_socket(conn, server_side=True) as tls:
                        with tls.makefile("rb") as stream:
                            stream.readline()
                            tls.sendall(b"250-audit\r\n250 AUTH PLAIN\r\n")
                            seen["auth"] = stream.readline().upper().startswith(b"AUTH")
                            tls.sendall(b"535 Dummy authentication refused\r\n")
                except (ssl.SSLError, ConnectionResetError):
                    seen["tls_aborted"] = True
        finally:
            listener.close()

    thread = Thread(target=peer, daemon=True)
    thread.start()
    result = SmtpEmailSender(host="127.0.0.1", port=port,
        username="dummy", password="not-a-real-secret", timeout=2).send(
            EmailMessage("fixture@example.com", "Fixture", "Synthetic", "<p>Synthetic</p>"))
    thread.join(timeout=4)
    assert not thread.is_alive()
    assert seen["starttls"] and seen["tls_aborted"]
    assert not seen["auth"]
    assert not result.success
