"""Trusted orchestration example. The model may propose args, never identity."""

import os
import sys
import uuid

from toolguard.client import GuardClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

client = GuardClient()
try:
    client.login("employee", os.getenv("ATG_DEMO_PASSWORD", "Demo-Only-2026!"))
    result = client.call("read_document", {"document_id": "pub-001"}, idempotency_key=uuid.uuid4().hex)
    print(result["status"], result["reason"])
    if result["status"] == "succeeded":
        print(result["result"]["body"])
finally:
    client.close()
