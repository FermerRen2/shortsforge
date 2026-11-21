"""Клиент DeepSeek: отбор моментов и заголовки по расшифровке.

Никаких сторонних SDK — обычный HTTP через стандартную библиотеку, чтобы приложение не тянуло
лишние зависимости. Ключ берётся из настроек (или из переменной окружения DEEPSEEK_API_KEY).
Ответ модели всегда просим в JSON и разбираем терпимо: модели любят обернуть его в ```json.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

SYSTEM_PROMPT = """Ты — монтажёр коротких вертикальных видео (Shorts, Reels, TikTok, VK Клипы).
Тебе дают расшифровку записи стрима с таймкодами. Твоя работа — найти моменты, которые
удержат зрителя с первых секунд.

Хороший момент:
- начинается со слова-крючка: вопрос, крик, неожиданность, смешная фраза, конфликт;
- понятен без контекста предыдущих часов;
- имеет завершение: панчлайн, реакция, развязка — а не обрывается на полуслове;
- длина 18–40 секунд;
- если в нём мат — это нормально, но не строй ролик на одном мате.

Плохой момент: перечисление предметов, чтение меню, тишина, реплики персонажей игры без
реакции стримера, реклама и начитка тарифов.

Верни СТРОГО JSON без пояснений:
{"clips": [{"start": "1:23:45", "end": "1:24:10", "title": "...", "hook": "...",
            "hashtags": "#shorts #gaming", "reason": "почему зайдёт"}]}

Правила для полей:
- start и end — таймкоды из расшифровки, формат ч:мм:сс или мм:сс;
- title — до 60 символов, живой язык, без мата (заменяй эвфемизмами), без кавычек-ёлочек;
- hook — фраза, которая звучит в первые 3 секунды;
- hashtags — 4–6 штук, начиная с #shorts;
- reason — одна короткая строка по-русски."""


class DeepSeekError(RuntimeError):
    pass


def _post(url: str, payload: dict, api_key: str, timeout: int = 120) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 401:
            raise DeepSeekError("ключ DeepSeek не принят (401). Проверьте ключ в настройках.") from e
        if e.code == 402:
            raise DeepSeekError("на балансе DeepSeek нет средств (402).") from e
        if e.code == 429:
            raise DeepSeekError("слишком много запросов (429). Подождите минуту.") from e
        raise DeepSeekError(f"DeepSeek вернул {e.code}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise DeepSeekError(f"нет связи с DeepSeek: {e.reason}") from e


def ask(api_key: str, messages: list[dict], model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com", temperature: float = 0.4,
        retries: int = 2) -> str:
    """Один запрос к чату. Возвращает текст ответа."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            data = _post(url, payload, api_key)
            return data["choices"][0]["message"]["content"]
        except DeepSeekError as e:
            last = e
            if "429" in str(e) or "связи" in str(e):
                time.sleep(2 + attempt * 3)
                continue
            raise
    raise DeepSeekError(str(last) if last else "не удалось получить ответ")


def ping(api_key: str, model: str = "deepseek-chat",
         base_url: str = "https://api.deepseek.com") -> str:
    """Проверка ключа: короткий запрос, в ответ ждём подтверждение."""
    text = ask(api_key, [{"role": "user", "content": 'Ответь JSON: {"ok": true}'}],
               model=model, base_url=base_url, temperature=0.0)
    return "ключ работает" if "ok" in text.lower() else f"странный ответ: {text[:80]}"


# --- разбор ответа -----------------------------------------------------------
def _parse_ts(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    parts = value.strip().replace(",", ".").split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return None


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise DeepSeekError("модель вернула не JSON")
    raw = text[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # частая беда — висячие запятые
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(cleaned)


def pick_moments(api_key: str, transcript: str, count: int, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com", language: str = "ru",
                 extra_notes: str = "") -> list[dict]:
    """Просит модель найти моменты. Возвращает список словарей start/end/title/..."""
    if not transcript.strip():
        raise DeepSeekError("расшифровка пуста — сначала распознайте речь")
    user = (
        f"Нужно {count} моментов для вертикальных роликов.\n"
        f"Язык речи: {language}.\n"
        + (f"Пожелания заказчика: {extra_notes}\n" if extra_notes else "")
        + "\nРасшифровка с таймкодами:\n" + transcript
    )
    content = ask(api_key, [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user}],
                  model=model, base_url=base_url, temperature=0.5)
    data = _extract_json(content)
    items = data.get("clips") or data.get("moments") or []
    out: list[dict] = []
    for it in items:
        start = _parse_ts(it.get("start"))
        end = _parse_ts(it.get("end"))
        if start is None or end is None or end <= start:
            continue
        if end - start < 8:
            end = start + 20
        if end - start > 60:
            end = start + 40
        out.append({
            "start": round(start, 1),
            "end": round(end, 1),
            "title": (it.get("title") or "").strip()[:80] or "Момент со стрима",
            "hook": (it.get("hook") or "").strip()[:120],
            "hashtags": (it.get("hashtags") or "#shorts").strip(),
            "reason": (it.get("reason") or "").strip()[:200],
            "source": "DeepSeek",
        })
    out.sort(key=lambda c: c["start"])
    return out[:count]
