import json

import requests

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, token, chat_ids):
        self.token = token
        self.chat_ids = [chat_ids] if isinstance(chat_ids, str) else list(chat_ids)

    def send(self, text, reply_markup=None, timeout=15):
        url = TELEGRAM_API_URL.format(token=self.token)
        errors = []
        for chat_id in self.chat_ids:
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
            if reply_markup is not None:
                data["reply_markup"] = json.dumps(reply_markup)
            resp = requests.post(url, data=data, timeout=timeout)
            if resp.status_code != 200:
                errors.append(f"chat_id={chat_id}: {resp.status_code} {resp.text}")
        if errors:
            raise RuntimeError("Telegram API error(s): " + "; ".join(errors))
