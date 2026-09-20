# capture.py
import json
import urllib.request
import uuid


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
        files = record.pop("_files", []) or []
        text = self._format(record)
        for chat_id in self.chats:
            try:
                if text.strip():
                    self._message(chat_id, text)
                for f in files:
                    self._document(chat_id, f)
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

        L = []

        # header
        L.append(f"{icon} <b>{_h(src.upper())}</b>")

        # identity line
        ident = []
        if r.get("sender"):
            ident.append(f"👤 <b>{_h(r.get('sender'))}</b>")
        if r.get("ip"):
            ident.append(f"🌐 <code>{_h(r.get('ip'))}</code>")
        if ident:
            L.append(" • ".join(ident))

        L.append(f"🕒 <code>{_h(r.get('ts'))}</code>")

        # request line
        L.append("")
        L.append("━━━━━━━━━━━━━━━━━━━━")
        L.append(f"<b>{_h(r.get('method'))}</b>  <code>{_h(r.get('path'))}</code>")
        L.append("━━━━━━━━━━━━━━━━━━━━")

        # user agent / referer
        if r.get("user_agent"):
            L.append(f"🧭 <i>{_h(r.get('user_agent'))[:180]}</i>")
        if r.get("referer"):
            L.append(f"🔗 <i>{_h(r.get('referer'))[:150]}</i>")

        # query
        q = r.get("query")
        if q and q not in ("{}", "null", "None"):
            L.append("")
            L.append("🔎 <b>Query</b>")
            L.append(f"<pre>{_h(q)[:600]}</pre>")

        # body
        b = r.get("body")
        if b:
            L.append("")
            L.append("📨 <b>Body</b>")
            L.append(f"<pre>{_h(b)[:600]}</pre>")

        # cookies
        c = r.get("cookies")
        if c and c not in ("{}", "null", "None"):
            L.append("")
            L.append("🍪 <b>Cookies</b>")
            L.append(f"<pre>{_h(c)[:400]}</pre>")

        # files
        fsum = r.get("files_summary")
        if fsum:
            L.append("")
            L.append("📎 <b>Files</b>")
            L.append(f"<pre>{_h(fsum)[:800]}</pre>")

        # error
        if r.get("error"):
            L.append("")
            L.append("⚠️ <b>Error</b>")
            L.append(f"<pre>{_h(r.get('error'))[:500]}</pre>")

        return "\n".join(L)

    # ---------------- telegram api ----------------

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

    def _document(self, chat_id, f):
        body, ctype = _multipart(
            fields={
                "chat_id": chat_id,
                "caption": f'📎 {f["filename"]} — {len(f["data"])} bytes',
            },
            files=[{
                "name": "document",
                "filename": f["filename"],
                "data": f["data"],
                "content_type": f.get("content_type", "application/octet-stream"),
            }],
        )
        req = urllib.request.Request(self._api("sendDocument"), data=body,
            headers={"Content-Type": ctype}, method="POST")
        urllib.request.urlopen(req, timeout=60).read()
