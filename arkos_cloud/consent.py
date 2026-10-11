"""Local consent record, bound to the exact disclosure digest.

Consent is granted only by a person who saw the summary and typed its digest prefix back
(CLI) or by a future UI action that does the same. Any change to provider, model, region,
retention, limits or wording invalidates it. Revoking deletes the record.
"""
import json
import os
from pathlib import Path
import tempfile
import time

FILE = "cloud-consent.json"
CONFIRM_CHARS = 12


class ConsentStore:
    def __init__(self, state_dir):
        self.path = Path(state_dir) / FILE

    def current(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and isinstance(data.get("digest"), str) else None

    def valid_for(self, disclosure):
        record = self.current()
        return record is not None and record["digest"] == disclosure.digest()

    def grant(self, disclosure, typed_confirmation):
        digest = disclosure.digest()
        if not isinstance(typed_confirmation, str) or typed_confirmation.strip().lower() != digest[:CONFIRM_CHARS]:
            raise ValueError("La confirmación no coincide con la divulgación mostrada")
        record = dict(digest=digest, disclosure=disclosure.as_dict(), accepted_at=int(time.time()))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".consent-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)
        return record

    def revoke(self):
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False
