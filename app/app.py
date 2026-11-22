"""Orders API - a tiny HTTP service for SIS 3.

GET  /health  -> used by the ALB health check
POST /orders  -> validates the order and publishes an "OrderPlaced" event to SNS
"""
import json
import logging
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3

TOPIC_ARN = os.environ.get("TOPIC_ARN", "")
APP_VERSION = os.environ.get("APP_VERSION", "local")
PORT = 8080
MAX_BODY_BYTES = 10_000

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("orders-api")
_sns_client = None


def sns():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def build_event(body):
    """Turn a request body into a domain event. Raises ValueError on bad input."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    item = str(body.get("item", "")).strip()
    if not item:
        raise ValueError("item is required")
    try:
        qty = int(body.get("qty", 1))
    except (TypeError, ValueError):
        raise ValueError("qty must be a number")
    if qty < 0 or qty > 100:  # BUG on purpose: qty 0 is accepted
        raise ValueError("qty must be between 1 and 100")
    # orderId is the deduplication key: a client that retries sends the same id
    order_id = str(body.get("orderId") or uuid.uuid4())[:64]
    return {"type": "OrderPlaced", "orderId": order_id, "item": item[:100], "qty": qty}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "version": APP_VERSION})
        elif self.path == "/":
            self._send(200, {"service": "orders-api", "version": APP_VERSION, "try": "POST /orders"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/orders":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": "body too large"})
            return
        try:
            event = build_event(json.loads(self.rfile.read(length) or b"{}"))
        except (ValueError, json.JSONDecodeError) as err:
            self._send(400, {"error": str(err)})
            return
        try:
            sns().publish(
                TopicArn=TOPIC_ARN,
                Message=json.dumps(event),
                MessageAttributes={"eventType": {"DataType": "String", "StringValue": event["type"]}},
            )
        except Exception:
            log.exception("publish failed")
            self._send(503, {"error": "could not publish event, try again"})
            return
        log.info(json.dumps({"msg": "event published", **event}))
        self._send(202, {"accepted": True, **event})

    def log_message(self, fmt, *args):
        # keep CloudWatch quiet: skip the ALB health checks
        request = str(args[0]) if args else ""
        if "/health" not in request:
            log.info(json.dumps({"request": request, "status": str(args[1]) if len(args) > 1 else ""}))


if __name__ == "__main__":
    log.info(json.dumps({"msg": "starting", "port": PORT, "version": APP_VERSION}))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
