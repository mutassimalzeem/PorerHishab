"""Durable polling worker: python -m app.services.notifications.worker."""
import argparse
import logging
import signal
from threading import Event

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.notifications.dispatcher import claim_pending_deliveries, process_single_delivery

logger = logging.getLogger(__name__)


def run_once(stop: Event | None = None) -> int:
    """Bounded memory and fresh leases: claim one item just before each provider call."""
    if not settings.NOTIFICATION_DELIVERY_ENABLED:
        return 0
    sent = 0
    for _ in range(max(1, min(settings.NOTIFICATION_BATCH_SIZE, 100))):
        if stop is not None and stop.is_set():
            break
        with SessionLocal() as db:
            rows = claim_pending_deliveries(db, limit=1)
            if not rows:
                break
            sent += process_single_delivery(db, rows[0])
    return sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if settings.NOTIFICATION_LEASE_SECONDS <= settings.SMTP_TIMEOUT_SECONDS * 4:
        raise ValueError("Lease must exceed four SMTP operation timeouts")
    if settings.NOTIFICATION_POLL_SECONDS <= 0:
        raise ValueError("Poll interval must be positive")
    stop = Event()
    def shutdown(*_):
        stop.set()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    logging.basicConfig(level=logging.INFO)
    while not stop.is_set():
        try:
            run_once(stop)
        except Exception:
            # Exception text may contain SQL parameters or provider data.
            logger.error("notification_worker_batch_failed")
            if args.once:
                raise
        if args.once:
            break
        stop.wait(settings.NOTIFICATION_POLL_SECONDS)


if __name__ == "__main__":
    main()
