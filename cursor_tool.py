import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import random
import string
import subprocess
import threading
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import imaplib
import email as email_lib
from email.header import decode_header
from email.utils import parsedate_to_datetime
import tempfile
import math
import ctypes
import traceback
import winreg
import socket
import struct
import select
import socketserver
from urllib.parse import urlparse, urlsplit, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Буфер обмена при вставке в браузер (регистрация) — потокобезопасно с pyperclip.
_CLIPBOARD_LOCK = threading.Lock()
_FILE_COMMIT_LOCK = threading.Lock()

# ─── COLORS ────────────────────────────────────────────────────────────────────
BG        = "#0d0d0f"
SURFACE   = "#141417"
SURFACE2  = "#1c1c21"
BORDER    = "#2a2a32"
ACCENT    = "#7c6aff"
ACCENT2   = "#5c4fff"
TEXT      = "#e8e8f0"
TEXT_DIM  = "#7070a0"
TEXT_MUTED= "#404060"
GREEN     = "#4ade80"
RED       = "#f87171"
YELLOW    = "#fbbf24"
SURFACE3  = "#101217"

# ─── DATA ──────────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "James","Oliver","Liam","Noah","Ethan","Mason","Logan","Lucas",
    "Henry","Aiden","Alexander","Sebastian","Jackson","Carter","Owen",
    "Wyatt","Julian","Gabriel","Isaac","Nathan","Dylan","Caleb","Ryan",
    "Adrian","Elijah","Hunter","Aaron","Charles","Thomas","Christian"
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Wilson","Taylor","Anderson","Thomas","Jackson","White","Harris",
    "Martin","Thompson","Young","Walker","Allen","Scott","King","Wright",
    "Baker","Nelson","Carter","Mitchell","Roberts","Phillips","Evans"
]

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def resource_path(relative_path):
    """
    Return absolute path to a bundled resource (PyInstaller onefile compatible).
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

def data_file_path(filename):
    """
    Path for mutable user files (mail/accounts), writable in source and exe mode.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.abspath(".")
    return os.path.join(base_dir, filename)

def crash_log_path():
    """Best-effort location for crash log file."""
    try:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".")
        return os.path.join(base_dir, "crash.log")
    except Exception:
        temp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or "."
        return os.path.join(temp_dir, "cursor_tool_crash.log")

def write_crash_log(kind, exc_type, exc_value, exc_tb):
    try:
        path = crash_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {kind}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Executable: {sys.executable}\n")
            f.write(f"Platform: {sys.platform}\n\n")
            f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            f.write("\n")
    except Exception:
        pass

def _global_excepthook(exc_type, exc_value, exc_tb):
    write_crash_log("UNHANDLED_EXCEPTION", exc_type, exc_value, exc_tb)
    # Keep default behavior (stderr / PyInstaller dialog if applicable).
    sys.__excepthook__(exc_type, exc_value, exc_tb)

def _threading_excepthook(args):
    write_crash_log("THREAD_EXCEPTION", args.exc_type, args.exc_value, args.exc_traceback)

def generate_password(length=12):
    # Simple password policy: only letters and digits.
    chars = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(random.choices(chars, k=length))
        if (any(c.isupper() for c in pwd) and
            any(c.islower() for c in pwd) and
            any(c.isdigit() for c in pwd)):
            return pwd

def _parse_email_credential_line(line):
    line = (line or "").strip()
    if not line:
        return None
    delim = None
    for d in [":", ";", "|", ",", "\t"]:
        if d in line:
            delim = d
            break
    if not delim:
        return None
    left, right = line.split(delim, 1)
    login = left.strip()
    password = right.strip()
    if login and password:
        return line, login, password
    return None

def count_email_credentials_in_file(path):
    """Count valid login/password lines (read-only, does not modify the file)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        return sum(1 for line in lines if _parse_email_credential_line(line))
    except Exception:
        return 0

def list_email_credentials_from_file(path):
    """Read all login/password pairs without modifying the file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        result = []
        for line in lines:
            parsed = _parse_email_credential_line(line)
            if parsed:
                result.append((parsed[1], parsed[2]))
        return result
    except Exception:
        return []

def remove_email_credentials_from_file(path, login):
    """Remove first line matching login from file."""
    login = (login or "").strip()
    if not login:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        rest = []
        removed = False
        for line in lines:
            if not removed:
                parsed = _parse_email_credential_line(line)
                if parsed and parsed[1] == login:
                    removed = True
                    continue
            rest.append(line)
        if not removed:
            return False
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rest) + ("\n" if rest else ""))
        return True
    except Exception:
        return False

def pop_email_credentials_from_file(path):
    """Read first login/password from file, remove it, return tuple or None."""
    creds = list_email_credentials_from_file(path)
    if not creds:
        return None
    login, password = creds[0]
    if remove_email_credentials_from_file(path, login):
        return login, password
    return None

def format_account_line(email_login, email_password, account_password):
    """email:pass или email:pass:cursor_pass если пароли различаются."""
    login = (email_login or "").strip()
    mail_pass = email_password or ""
    acc_pass = account_password or ""
    if acc_pass and acc_pass != mail_pass:
        return f"{login}:{mail_pass}:{acc_pass}\n"
    return f"{login}:{mail_pass}\n"

def save_account(first, last, email_login, email_password, account_password, filepath="accounts.txt"):
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(format_account_line(email_login, email_password, account_password))

# ─── APP CONFIG ──────────────────────────────────────────────────────────────
APP_CONFIG_FILENAME = "cursor_tool_config.json"
# Cloudflare часто режет запросы с User-Agent Python-urllib (ошибка 1010).
_HTTP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

def _app_config_path():
    r"""
    Standard Windows location for app configuration: %LOCALAPPDATA%\CursorTool
    """
    appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if appdata:
        config_dir = os.path.join(appdata, "CursorTool")
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception:
            pass
        new_path = os.path.join(config_dir, APP_CONFIG_FILENAME)
        
        # Migration logic: if old config exists in the script folder, move it to the new location.
        old_path = data_file_path(APP_CONFIG_FILENAME)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                import shutil
                shutil.move(old_path, new_path)
            except Exception:
                pass
        return new_path
    return data_file_path(APP_CONFIG_FILENAME)

def load_app_config():
    try:
        path = _app_config_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_app_config_values(**updates):
    cfg = load_app_config()
    cfg.update(updates)
    try:
        with open(_app_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ─── EMAIL (Rambler IMAP) ────────────────────────────────────────────────────
RAMBLER_IMAP_HOST = "imap.rambler.ru"
RAMBLER_IMAP_PORT = 993
ACCOUNT_PASSWORD_MODES = ("generated", "email", "custom")

def resolve_account_password(mode, email_password="", custom_password=""):
    """Пароль для регистрации Cursor: сгенерированный, от почты или свой."""
    m = (mode or "generated").strip().lower()
    if m == "email":
        ep = (email_password or "").strip()
        return ep if ep else generate_password()
    if m == "custom":
        cp = (custom_password or "").strip()
        return cp if cp else generate_password()
    return generate_password()

def _decode_email_header(value):
    if not value:
        return ""
    chunks = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            chunks.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(part or "")
    return "".join(chunks).strip()

def _email_message_plain_text(msg):
    """Текст письма (plain; при отсутствии — упрощённый HTML)."""
    if msg.is_multipart():
        plain_parts, html_parts = [], []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            ctype = (part.get_content_type() or "").lower()
            if ctype == "text/plain":
                plain_parts.append(text)
            elif ctype == "text/html":
                html_parts.append(text)
        if plain_parts:
            return "\n".join(plain_parts).strip()
        if html_parts:
            t = html_parts[0]
            t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", t)
            t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
            t = re.sub(r"<[^>]+>", " ", t)
            return re.sub(r"\s+", " ", t).strip()
        return ""

    payload = msg.get_payload(decode=True)
    if not payload:
        return (msg.get_payload() or "").strip()
    charset = msg.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    if (msg.get_content_type() or "").lower() == "text/html":
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text.strip()

def _email_date_key(msg):
    try:
        dt = parsedate_to_datetime(msg.get("Date") or "")
        return int(dt.timestamp()) if dt else 0
    except Exception:
        return 0

def rambler_fetch_code_best_effort(email_addr, password):
    """
    Чтение ящика Rambler по IMAP; поиск кода подтверждения только в письмах от Cursor.
    Возвращает (data, code, meta, n_letters, err_str).
    """
    login = (email_addr or "").strip()
    pwd = password or ""
    if not login or not pwd:
        return None, None, None, 0, "Не указаны логин или пароль почты Rambler."

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(RAMBLER_IMAP_HOST, RAMBLER_IMAP_PORT)
        mail.login(login, pwd)
        status, _ = mail.select("INBOX")
        if status != "OK":
            return None, None, None, 0, "Не удалось открыть папку INBOX."

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            return None, None, None, 0, "Не удалось получить список писем."

        ids = messages[0].split() if messages and messages[0] else []
        if not ids:
            return None, None, None, 0, None

        letters = []
        for eid in reversed(ids[-25:]):
            status, data = mail.fetch(eid, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                continue
            raw = data[0][1]
            if not raw:
                continue
            msg = email_lib.message_from_bytes(raw)
            subj = _decode_email_header(msg.get("Subject"))
            sender = _decode_email_header(msg.get("From"))
            body = _email_message_plain_text(msg)
            letters.append({
                "subject": subj,
                "sender": sender,
                "sender_name": "",
                "date": _email_date_key(msg),
                "letter": {"text": body, "html": ""},
            })

        if not letters:
            return None, None, None, 0, None

        cursor_letters = [L for L in letters if _is_cursor_email(L)]
        if not cursor_letters:
            return None, None, None, len(letters), None

        ordered = _letters_ordered_for_code_search(cursor_letters)
        for letter in ordered:
            code = _extract_code_from_single_letter(letter)
            if code:
                meta = f"{letter.get('subject') or ''} | {letter.get('sender') or ''}".strip(" |")
                return letter, code, meta, len(cursor_letters), None

        newest = max(cursor_letters, key=_letter_date_key)
        meta = f"{newest.get('subject') or ''} | {newest.get('sender') or ''}".strip(" |")
        return newest, None, meta, len(cursor_letters), None
    except imaplib.IMAP4.error as e:
        return None, None, None, 0, f"Ошибка IMAP Rambler: {e}"
    except OSError as e:
        return None, None, None, 0, f"Сеть/IMAP Rambler: {e}"
    except Exception as e:
        return None, None, None, 0, str(e)
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass

def fetch_verification_code_best_effort(email, password):
    """Чтение кода подтверждения из почты Rambler (только письма от Cursor)."""
    return rambler_fetch_code_best_effort(email, password)

# ─── BRINGSMS (SMS-Activate compatible) ───────────────────────────────────────
BRINGSMS_API_BASE = "https://api.bring-sms.store/stubs/handler_api.php"
BRINGSMS_SERVICE_ANY_OTHER = "ot"

def _parse_rub_price(value):
    """Парсит сумму в ₽ из поля UI: 5, 5.5, 5р, 5 ₽ и т.п."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def _bringsms_ot_entry(services):
    """
    Запись цены Any Other (ot) из getPrices.
    С service=ot API отдаёт {cost, count} напрямую; без service — {ot: {cost, count}}.
    """
    if not isinstance(services, dict):
        return None
    nested = services.get(BRINGSMS_SERVICE_ANY_OTHER)
    if isinstance(nested, dict):
        return nested
    if any(k in services for k in ("cost", "price", "count")):
        return services
    return None

def bringsms_api_call(api_key, action, timeout=25, **extra):
    params = {"api_key": (api_key or "").strip(), "action": action}
    for k, v in extra.items():
        if v is not None and v != "":
            params[k] = v
    url = f"{BRINGSMS_API_BASE}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": _HTTP_UA, "Accept": "text/plain, application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"BringSMS HTTP {e.code}: {err_body or e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"BringSMS сеть: {e.reason}") from e

def bringsms_get_countries(api_key):
    raw = bringsms_api_call(api_key, "getCountries", timeout=20)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}

def bringsms_find_cheapest_ot_country(api_key, max_price=None):
    raw = bringsms_api_call(api_key, "getPrices", service=BRINGSMS_SERVICE_ANY_OTHER, timeout=25)
    try:
        prices = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"BringSMS getPrices: неожиданный ответ: {raw[:200]}") from exc

    if not isinstance(prices, dict):
        raise RuntimeError(f"BringSMS getPrices: неожиданный ответ: {raw[:200]}")

    best = None
    cheapest_over_limit = None
    max_p = _parse_rub_price(max_price)

    for country_id, services in prices.items():
        if country_id in ("detail", "info", "error"):
            continue
        svc = _bringsms_ot_entry(services)
        if not isinstance(svc, dict):
            continue
        try:
            cost = float(svc.get("cost") or svc.get("price") or 0)
            count = int(svc.get("count") or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0 or cost <= 0:
            continue
        try:
            cid = int(country_id)
        except (TypeError, ValueError):
            continue
        if cheapest_over_limit is None or cost < cheapest_over_limit[0]:
            cheapest_over_limit = (cost, cid, count)
        if max_p is not None and cost > max_p:
            continue
        if best is None or cost < best[0]:
            best = (cost, cid, count)

    if best is None:
        if max_p is not None:
            if cheapest_over_limit is not None:
                cmin = cheapest_over_limit[0]
                raise RuntimeError(
                    f"Нет номеров Any Other не дороже {max_p:g} ₽ "
                    f"(самый дешёвый сейчас ~{cmin:g} ₽)"
                )
            raise RuntimeError(f"Нет номеров Any Other не дороже {max_p:g} ₽")
        raise RuntimeError("Нет доступных номеров Any Other (ot)")
    return best[1], best[0]

def bringsms_buy_number(api_key, country_id, max_price=None):
    kwargs = {"service": BRINGSMS_SERVICE_ANY_OTHER, "country": int(country_id)}
    max_p = _parse_rub_price(max_price)
    if max_p is not None:
        kwargs["maxPrice"] = max_p
    raw = bringsms_api_call(api_key, "getNumber", timeout=30, **kwargs)
    if raw.startswith("ACCESS_NUMBER:"):
        parts = raw.split(":")
        if len(parts) >= 3:
            return parts[1], parts[2]
    raise RuntimeError(f"BringSMS getNumber: {raw}")

def bringsms_set_status(api_key, activation_id, status):
    return bringsms_api_call(api_key, "setStatus", id=str(activation_id), status=int(status))

def bringsms_poll_sms_code(api_key, activation_id, timeout=300, poll_interval=5, log_cb=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = bringsms_api_call(api_key, "getStatus", id=str(activation_id), timeout=20)
        if raw.startswith("STATUS_OK:"):
            return raw.split(":", 1)[1].strip()
        if raw == "STATUS_WAIT_CODE":
            if log_cb:
                log_cb("BringSMS: жду SMS…")
            time.sleep(poll_interval)
            continue
        if raw == "STATUS_CANCEL":
            raise RuntimeError("Активация номера отменена (STATUS_CANCEL)")
        time.sleep(poll_interval)
    raise TimeoutError("SMS-код не пришёл за отведённое время")

def _normalize_phone_digits(phone):
    return re.sub(r"\D", "", phone or "")

def bringsms_split_phone_for_ui(phone, country_id, countries_data=None):
    digits = _normalize_phone_digits(phone)
    dial = ""
    if countries_data:
        info = countries_data.get(str(country_id)) or countries_data.get(country_id)
        if isinstance(info, dict):
            dial = _normalize_phone_digits(str(info.get("phone") or info.get("dial") or ""))
    if dial and digits.startswith(dial):
        local = digits[len(dial):]
    elif dial and digits.startswith("0" + dial):
        local = digits[len(dial) + 1:]
    else:
        local = digits
        dial = dial or ""
    dial_display = f"+{dial}" if dial else "+"
    return dial_display, local

def bringsms_buy_cheapest_ot(api_key, max_price=None, log_cb=None):
    country_id, cost = bringsms_find_cheapest_ot_country(api_key, max_price)
    if log_cb:
        log_cb(f"BringSMS: Any Other, страна {country_id}, цена ~{cost:g} ₽")
    buy_max = _parse_rub_price(max_price)
    if buy_max is None:
        buy_max = cost
    activation_id, phone = bringsms_buy_number(api_key, country_id, max_price=buy_max)
    countries = bringsms_get_countries(api_key)
    dial, local = bringsms_split_phone_for_ui(phone, country_id, countries)
    return activation_id, phone, country_id, dial, local

def _letter_plain_text(letter_item):
    inner = letter_item.get("letter") or {}
    text = (inner.get("text") or "").strip()
    if text:
        return text
    html = inner.get("html") or ""
    if not html:
        return ""
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _is_cursor_email(letter_item):
    """Письмо от Cursor (по отправителю или теме)."""
    subj = (letter_item.get("subject") or "").lower()
    sender = (letter_item.get("sender") or "").lower()
    sender_name = (letter_item.get("sender_name") or "").lower()
    return "cursor" in f"{subj} {sender} {sender_name}"

def _is_verification_email_subject(subj):
    """Тема вроде «Подтвердите ваш адрес электронной почты» и близкие варианты (RU/EN)."""
    s = (subj or "").strip().lower().replace("ё", "е")
    if not s:
        return False
    if "подтвердите" in s or "подтвержден" in s:
        if any(k in s for k in ("почт", "электрон", "адрес", "email", "e-mail", "eмейл")):
            return True
    if "confirm" in s and ("email" in s or "mail" in s):
        return True
    if "verify" in s and ("email" in s or "e-mail" in s or "address" in s):
        return True
    return False

def _letter_date_key(item):
    try:
        return int(item.get("date") or 0)
    except (TypeError, ValueError):
        return 0

def _letters_ordered_for_code_search(letters):
    """Сначала письма с темой подтверждения почты (новые выше), затем остальные по дате."""
    by_date = sorted(letters, key=_letter_date_key, reverse=True)
    pri, rest = [], []
    for L in by_date:
        (pri if _is_verification_email_subject(L.get("subject")) else rest).append(L)
    return pri + rest

_YEAR_LIKE_CODE = re.compile(r"^(19|20)\d{2}$")

def _score_verification_code(code, context_lower):
    score = 0
    if not code or not code.isdigit():
        return -1
    if len(code) == 6:
        score += 100
    elif len(code) == 5:
        score += 55
    elif len(code) in (4, 7, 8):
        score += 25
    if _YEAR_LIKE_CODE.match(code):
        score -= 90
    if any(k in context_lower for k in ("code", "код", "otp", "verification", "verify", "confirm", "подтверд")):
        score += 45
    return score

def _extract_code_from_text_blob(text):
    if not text:
        return None
    best_code = None
    best_score = -1
    for m in re.finditer(r"\b(\d{6})\b", text):
        code = m.group(1)
        ctx = text[max(0, m.start() - 50): m.end() + 30].lower()
        sc = _score_verification_code(code, ctx)
        if sc > best_score:
            best_score = sc
            best_code = code
    for m in re.finditer(
        r"(?i)(?:code|код|otp|pin|verification|verify|confirm|подтверд)[^\d]{0,50}(\d{4,8})\b",
        text,
    ):
        code = m.group(1)
        if _YEAR_LIKE_CODE.match(code):
            continue
        ctx = text[max(0, m.start() - 20): m.end() + 20].lower()
        sc = _score_verification_code(code, ctx)
        if sc > best_score:
            best_score = sc
            best_code = code
    if best_code and best_score > 0:
        return best_code
    for m in re.finditer(r"(?<![\d])(\d{4,8})(?![\d])", text):
        code = m.group(1)
        if _YEAR_LIKE_CODE.match(code) or len(code) != 6:
            continue
        return code
    return None

def _extract_code_from_single_letter(letter_item):
    body = _letter_plain_text(letter_item)
    subj = letter_item.get("subject") or ""
    sender = (letter_item.get("sender") or "") + " " + (letter_item.get("sender_name") or "")
    for source in (body, subj, sender):
        code = _extract_code_from_text_blob(source)
        if code:
            return code
    return None

def _windows_http_url_progid():
    """ProgId браузера по умолчанию для http(s) в Windows."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        ) as key:
            return (winreg.QueryValueEx(key, "Progid")[0] or "").strip()
    except OSError:
        return ""

def _set_page_load_eager(options):
    """Не ждать полной загрузки всех ресурсов — меньше «висит» на пустой странице / data:."""
    try:
        options.page_load_strategy = "eager"
    except Exception:
        try:
            options.set_capability("pageLoadStrategy", "eager")
        except Exception:
            pass

def _configure_chromium_stealth_options(options):
    """Меньше признаков автоматизации: без баннера «управляет тестовое ПО» и без AutomationControlled."""
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

def _chromium_apply_stealth_cdp(driver):
    """Скрывает navigator.webdriver на новых документах (дополнительно к флагам запуска)."""
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    try { delete navigator.__proto__.webdriver; } catch (e) {}
                    if (!window.chrome) { window.chrome = { runtime: {} }; }
                """
            },
        )
    except Exception:
        pass

def _chromium_temp_user_data_arg(instance_index):
    """Временный профиль Chromium: отдельные куки/хранилище на каждую регистрацию и параллельные окна."""
    if instance_index is None:
        return None
    d = tempfile.mkdtemp(prefix=f"cursor_reg_{instance_index}_")
    return f"--user-data-dir={d}"


def _chromium_lang_for_instance(instance_index):
    """Разные Accept-Language между окнами (не идентичные настройки сессии)."""
    if instance_index is None:
        return None
    langs = (
        "ru-RU,ru",
        "en-US,en",
        "en-GB,en",
        "de-DE,de",
        "fr-FR,fr",
        "es-ES,es",
    )
    return langs[instance_index % len(langs)]


def _windows_primary_work_area():
    """Рабочая область монитора (с учётом панели задач), Win32."""
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    r = RECT()
    SPI_GETWORKAREA = 0x0030
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(r), 0
        )
        if ok:
            w = r.right - r.left
            h = r.bottom - r.top
            if w > 80 and h > 80:
                return int(r.left), int(r.top), w, h
    except Exception:
        pass
    w = int(ctypes.windll.user32.GetSystemMetrics(0))
    h = int(ctypes.windll.user32.GetSystemMetrics(1))
    return 0, 0, w, h


def _tile_rect_for_browser(instance_index, total, gap=8):
    """
    Прямоугольник окна браузера на экране: сетка ~sqrt(N) столбцов,
    чтобы 2–5 окон не перекрывали друг друга.
    """
    wx, wy, ww, wh = _windows_primary_work_area()
    if total <= 1:
        return wx, wy, ww, wh
    cols = max(1, int(math.ceil(math.sqrt(total))))
    rows = max(1, int(math.ceil(total / cols)))
    usable_w = max(1, ww - gap * (cols + 1))
    usable_h = max(1, wh - gap * (rows + 1))
    cw = max(1, usable_w // cols)
    ch = max(1, usable_h // rows)
    col = instance_index % cols
    row = instance_index // cols
    x = wx + gap + col * (cw + gap)
    y = wy + gap + row * (ch + gap)
    x += random.randint(-2, 2)
    y += random.randint(-2, 2)
    return x, y, cw, ch


def selenium_apply_window_layout(driver, instance_index, parallel_total):
    """Одно окно — на весь экран; несколько — плиткой по рабочей области."""
    try:
        if parallel_total <= 1:
            driver.maximize_window()
            return
        x, y, w, h = _tile_rect_for_browser(instance_index, parallel_total)
        driver.set_window_rect(x=x, y=y, width=w, height=h)
    except Exception:
        try:
            driver.maximize_window()
        except Exception:
            pass


def selenium_create_driver_windows_default(log_fn=None, instance_index=None):
    """
    WebDriver под системный браузер по умолчанию (Edge / Chrome / Firefox).
    При ошибке перебирает другие варианты.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions

    log_fn = log_fn or (lambda _m: None)
    pl = _windows_http_url_progid().lower()
    ud_arg = _chromium_temp_user_data_arg(instance_index)
    lang_arg = _chromium_lang_for_instance(instance_index)

    def edge():
        o = EdgeOptions()
        o.add_experimental_option("detach", True)
        _set_page_load_eager(o)
        _configure_chromium_stealth_options(o)
        o.add_argument("--window-size=1366,768")
        if lang_arg:
            o.add_argument(f"--lang={lang_arg}")
        if ud_arg:
            o.add_argument(ud_arg)
        drv = webdriver.Edge(options=o)
        _chromium_apply_stealth_cdp(drv)
        return drv

    def chrome():
        try:
            import undetected_chromedriver as uc
            o = uc.ChromeOptions()
            _set_page_load_eager(o)
            o.add_argument("--window-size=1366,768")
            if lang_arg:
                o.add_argument(f"--lang={lang_arg}")
            if ud_arg:
                o.add_argument(ud_arg)
            drv = uc.Chrome(options=o)
            return drv
        except ImportError:
            o = ChromeOptions()
            o.add_experimental_option("detach", True)
            _set_page_load_eager(o)
            _configure_chromium_stealth_options(o)
            o.add_argument("--window-size=1366,768")
            if lang_arg:
                o.add_argument(f"--lang={lang_arg}")
            if ud_arg:
                o.add_argument(ud_arg)
            drv = webdriver.Chrome(options=o)
            _chromium_apply_stealth_cdp(drv)
            return drv

    def firefox():
        from selenium.webdriver.firefox.options import Options as FirefoxOptions

        o = FirefoxOptions()
        o.set_preference("dom.webdriver.enabled", False)
        return webdriver.Firefox(options=o)

    named = []
    if "firefox" in pl:
        named.append(("Firefox", firefox))
    if "chrome" in pl or "chromium" in pl or "brave" in pl:
        named.append(("Chrome", chrome))
    if "edge" in pl or "msedge" in pl:
        named.append(("Edge", edge))
    if not named:
        named = [("Edge", edge), ("Chrome", chrome), ("Firefox", firefox)]
    else:
        for label, fn in (("Edge", edge), ("Chrome", chrome), ("Firefox", firefox)):
            if fn not in [x[1] for x in named]:
                named.append((label, fn))

    last_err = None
    for label, factory in named:
        try:
            drv = factory()
            hint = pl or "не задан"
            log_fn(f"Регистрация: браузер для автоматизации — {label} (ProgId http: {hint})")
            return drv
        except Exception as e:
            last_err = e
            log_fn(f"⚠ Не удалось запустить {label}: {e}")
    raise last_err

def get_chrome_version():
    """Мажорная версия Chrome (например 148) или None."""
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return str(version).split(".")[0]
        except OSError:
            continue
    return None

def _chrome_major_version():
    v = get_chrome_version()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None

def _uc_likely_supported(chrome_major):
    """undetected_chromedriver часто отстаёт от свежего Chrome и зависает на скачивании драйвера."""
    if chrome_major is None:
        return True
    return 100 <= chrome_major <= 145

def _run_driver_factory_with_timeout(label, factory, log_fn, timeout_sec=60):
    """Запуск драйвера в отдельном потоке — не зависать бесконечно на uc.Chrome()."""
    log_fn(f"{label}: ожидание запуска (до {timeout_sec} сек)…")
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(factory)
        try:
            return fut.result(timeout=timeout_sec), None
        except FuturesTimeoutError:
            log_fn(f"⚠ {label}: таймаут {timeout_sec} сек — пробуем другой способ.")
            return None, TimeoutError(f"{label}: таймаут {timeout_sec} сек")
        except Exception as e:
            return None, e

def _build_registration_chrome_options(ChromeOptions, *, ud_arg=None, lang_arg=None):
    o = ChromeOptions()
    o.add_experimental_option("detach", True)
    _set_page_load_eager(o)
    _configure_chromium_stealth_options(o)
    o.add_argument("--window-size=1366,768")
    o.add_argument("--no-first-run")
    o.add_argument("--no-default-browser-check")
    if lang_arg:
        o.add_argument(f"--lang={lang_arg}")
    if ud_arg:
        o.add_argument(ud_arg)
    return o

def selenium_create_registration_driver(log_fn=None, instance_index=None):
    """
    Драйвер для регистрации: Chrome через Selenium Manager, затем undetected (если версия
    поддерживается), затем системный браузер по умолчанию.
    instance_index: для Chromium — временный user-data-dir и свой --lang на каждое окно (0, 1, …).
    Если None — без отдельного профиля и без смены языка (для совместимости).
    """
    log_fn = log_fn or (lambda _m: None)
    log_fn("Запуск браузера для регистрации...")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions

    chrome_major = _chrome_major_version()
    if chrome_major:
        log_fn(f"Обнаружена версия Chrome: {chrome_major}")

    ud_arg = _chromium_temp_user_data_arg(instance_index)
    lang_arg = _chromium_lang_for_instance(instance_index)

    # Попытка 1: Chrome + Selenium Manager (надёжно для свежих версий вроде 148)
    def _start_selenium_chrome():
        o = _build_registration_chrome_options(
            ChromeOptions, ud_arg=ud_arg, lang_arg=lang_arg
        )
        drv = webdriver.Chrome(options=o)
        _chromium_apply_stealth_cdp(drv)
        return drv

    drv, err = _run_driver_factory_with_timeout(
        "Chrome (Selenium Manager)", _start_selenium_chrome, log_fn, timeout_sec=60
    )
    if drv is not None:
        log_fn("✓ Chrome WebDriver запущен (Selenium Manager)")
        return drv
    if err and not isinstance(err, TimeoutError):
        log_fn(f"⚠ Chrome (Selenium Manager): {err}")

    # Попытка 2: undetected_chromedriver — только для «стабильных» версий Chrome
    try:
        import undetected_chromedriver as uc
        has_uc = True
    except ImportError:
        has_uc = False

    if has_uc and _uc_likely_supported(chrome_major):
        def _start_uc_chrome():
            o = uc.ChromeOptions()
            _set_page_load_eager(o)
            o.add_argument("--window-size=1366,768")
            o.add_argument("--no-first-run")
            o.add_argument("--no-default-browser-check")
            o.add_argument("--disable-blink-features=AutomationControlled")
            if lang_arg:
                o.add_argument(f"--lang={lang_arg}")
            if ud_arg:
                o.add_argument(ud_arg)
            kwargs = {"options": o, "use_subprocess": True}
            if chrome_major:
                kwargs["version_main"] = chrome_major
            return uc.Chrome(**kwargs)

        log_fn("Пробуем undetected_chromedriver…")
        drv, err = _run_driver_factory_with_timeout(
            "undetected_chromedriver", _start_uc_chrome, log_fn, timeout_sec=45
        )
        if drv is not None:
            log_fn("✓ undetected_chromedriver запущен успешно")
            return drv
        if err and not isinstance(err, TimeoutError):
            log_fn(f"⚠ undetected_chromedriver: {err}")
    elif has_uc and chrome_major:
        log_fn(
            f"Chrome {chrome_major} слишком новый для undetected_chromedriver — "
            "пропускаем (часто зависает на подборе драйвера)."
        )

    # Попытка 3: системный браузер по умолчанию (Edge / Firefox)
    try:
        log_fn("Попытка системного браузера по умолчанию…")
        drv, err = _run_driver_factory_with_timeout(
            "Системный браузер",
            lambda: selenium_create_driver_windows_default(log_fn, instance_index=instance_index),
            log_fn,
            timeout_sec=60,
        )
        if drv is not None:
            return drv
        if err:
            log_fn(f"✗ Системный браузер: {err}")
    except Exception as e:
        log_fn(f"✗ Ошибка системного браузера: {e}")

    messagebox.showerror("Ошибка браузера",
        "Не удалось запустить браузер.\n\n"
        "Решения:\n"
        "1. Обновите Google Chrome и Microsoft Edge\n"
        "2. Закройте зависшие процессы chrome.exe / chromedriver.exe в диспетчере задач\n"
        "3. Установите: pip install selenium undetected-chromedriver")
    raise Exception("Не удалось создать WebDriver")

def _human_move_and_click(driver, element, *, quick=False):
    """
    Подвести курсор к элементу с короткими «дрожащими» шагами и нажать.
    Кнопки и поля ввода. quick=True — укороченная траектория (например OTP по ячейкам).
    """
    from selenium.webdriver.common.action_chains import ActionChains

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(random.uniform(0.02, 0.06) if quick else random.uniform(0.04, 0.11))
    try:
        ac = ActionChains(driver)
        ox = random.randint(-10, 10) if quick else random.randint(-14, 14)
        oy = random.randint(-5, 5) if quick else random.randint(-8, 8)
        ac.move_to_element_with_offset(element, ox, oy)
        n_steps = random.randint(1, 2) if quick else random.randint(2, 5)
        w = 3 if quick else 5
        for _ in range(n_steps):
            ac.move_by_offset(random.randint(-w, w), random.randint(-w, w))
            ac.pause(
                random.uniform(0.01, 0.03)
                if quick
                else random.uniform(0.015, 0.045)
            )
        ac.move_by_offset(random.randint(-2, 2), random.randint(-2, 2))
        ac.pause(
            random.uniform(0.03, 0.07)
            if quick
            else random.uniform(0.05, 0.12)
        )
        ac.click()
        ac.perform()
    except Exception:
        element.click()

def _selenium_paste_human(driver, element, text, *, quick=False):
    """
    Как вручную: клик в поле, очистка, вставка из буфера (Ctrl+V).
    Снижает срабатывание капчи по сравнению с посимвольным send_keys.
    """
    from selenium.webdriver.common.keys import Keys

    if text is None:
        return
    text = str(text)
    _human_move_and_click(driver, element, quick=quick)
    time.sleep(random.uniform(0.07, 0.18))
    try:
        element.clear()
    except Exception:
        pass
    time.sleep(random.uniform(0.06, 0.14))
    try:
        import pyperclip
        from selenium.webdriver.common.action_chains import ActionChains
        # Вся последовательность под замком: иначе параллельные окна затирают буфер друг другу.
        with _CLIPBOARD_LOCK:
            pyperclip.copy(text)
            time.sleep(random.uniform(0.12, 0.25))

            # Попытка 1: ActionChains (эмуляция реального нажатия клавиш)
            try:
                ac = ActionChains(driver)
                ac.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            except Exception:
                # Попытка 2: Передача через send_keys (fallback)
                element.send_keys(Keys.CONTROL + "v")

            # Попытка 3: Эмуляция события вставки через JS (для сложных OTP-полей)
            time.sleep(0.1)
            driver.execute_script("""
                var el = arguments[0];
                var val = arguments[1];
                if (el.value.length < val.length) {
                    var data = new DataTransfer();
                    data.setData('text/plain', val);
                    var ev = new ClipboardEvent('paste', {
                        clipboardData: data,
                        bubbles: true,
                        cancelable: true
                    });
                    el.dispatchEvent(ev);
                    // Если после пасты все еще пусто или мало символов, пробуем прямо в value (fallback)
                    if (el.value.length < 1) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            """, element, text)
    except Exception:
        _selenium_type_human(driver, element, text, fast=quick)
        return
    time.sleep(random.uniform(0.1, 0.22))

def _selenium_type_into(driver, element, text):
    try:
        element.click()
    except Exception:
        pass
    try:
        element.clear()
    except Exception:
        pass
    try:
        element.send_keys(text)
    except Exception:
        driver.execute_script(
            "arguments[0].focus && arguments[0].focus();"
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            element,
            text,
        )

def _selenium_type_human(driver, element, text, *, fast=False):
    """
    Ввод по символам со случайными паузами (как при наборе с клавиатуры).
    Не подставляет value через JS — так реже триггерится антибот.
    """
    from selenium.webdriver.common.keys import Keys

    if text is None:
        return
    text = str(text)
    try:
        _human_move_and_click(driver, element, quick=fast)
    except Exception:
        try:
            element.click()
        except Exception:
            pass
    time.sleep(random.uniform(0.04, 0.1))
    try:
        element.clear()
    except Exception:
        pass
    time.sleep(random.uniform(0.05, 0.12))
    lo, hi = (0.02, 0.048) if fast else (0.038, 0.088)
    for ch in text:
        element.send_keys(ch)
        if ch in " @._-+":
            time.sleep(random.uniform(0.07, 0.14))
        else:
            time.sleep(random.uniform(lo, hi))
        if not fast and random.random() < 0.038:
            time.sleep(random.uniform(0.1, 0.28))

def _selenium_click_first(driver, candidates, timeout_each=6, humanize=False):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, timeout_each).until(EC.element_to_be_clickable((by, sel)))
            if humanize:
                time.sleep(random.uniform(0.08, 0.22))
                _human_move_and_click(driver, el)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.12)
                el.click()
            return True
        except Exception:
            continue
    return False

def _selenium_find_phone_input_pair(driver):
    """Пара полей: код страны (+212) и остальные цифры номера."""
    from selenium.webdriver.common.by import By

    cc = [e for e in driver.find_elements(By.CSS_SELECTOR, "input[autocomplete='tel-country-code']") if e.is_displayed()]
    nat = [e for e in driver.find_elements(By.CSS_SELECTOR, "input[autocomplete='tel-national']") if e.is_displayed()]
    if cc and nat:
        return cc[0], nat[0]

    tel_inputs = [
        e for e in driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='tel'], input[name*='phone'], input[name*='Phone'], "
            "input[placeholder*='+' i], input[placeholder*='телефон' i], input[placeholder*='phone' i]",
        )
        if e.is_displayed()
    ]
    if len(tel_inputs) >= 2:
        return tel_inputs[0], tel_inputs[1]

    for label_hint in ("телефон", "phone", "mobile", "номер"):
        try:
            inputs = driver.find_elements(
                By.XPATH,
                f"//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label_hint}')]"
                f"/following::input[not(@type='hidden')][1]"
                f"|//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label_hint}')]"
                f"/following::input[not(@type='hidden')][2]",
            )
            vis = [e for e in inputs if e.is_displayed()]
            if len(vis) >= 2:
                return vis[0], vis[1]
        except Exception:
            continue
    return None, None

def _selenium_wait_phone_fields(driver, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        cc, nat = _selenium_find_phone_input_pair(driver)
        if cc and nat:
            return cc, nat
        time.sleep(1)
    return None, None

def _selenium_find_otp_fields(driver):
    from selenium.webdriver.common.by import By

    multi = driver.find_elements(By.CSS_SELECTOR, "input[inputmode='numeric'][maxlength='1']")
    vis_multi = [e for e in multi if e.is_displayed()]
    if len(vis_multi) >= 4:
        return None, vis_multi
    for by, sel in (
        (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
        (By.CSS_SELECTOR, "input[inputmode='numeric']"),
        (By.XPATH, "//input[contains(@placeholder,'код') or contains(@placeholder,'Код') or contains(@placeholder,'code') or contains(@placeholder,'Code')]"),
    ):
        for el in driver.find_elements(by, sel):
            try:
                t = (el.get_attribute("type") or "").lower()
                if t in ("password", "email", "hidden"):
                    continue
                if el.is_displayed() and el.get_attribute("maxlength") != "1":
                    return el, None
            except Exception:
                continue
    return None, None

def _selenium_wait_registration_success(driver, timeout=120):
    """Ждёт подтверждения успешной регистрации по URL."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = (driver.current_url or "").lower()
        except Exception:
            url = ""
        if "cursor.com" in url and "sign-up" not in url and "login" not in url:
            return True
        if "authenticator.cursor.sh" in url and "/sign-up" not in url:
            return True
        time.sleep(2)
    return False

def _refresh_internet_settings():
    INTERNET_OPTION_SETTINGS_CHANGED = 39
    INTERNET_OPTION_REFRESH = 37
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)

def _broadcast_env_change():
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        2000,
        None
    )

def _set_user_env(name, value):
    env_key = r"Environment"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, env_key, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)

def _delete_user_env(name):
    env_key = r"Environment"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, env_key, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass

# Local HTTP proxy → SOCKS5 (Windows WinINet does not apply SOCKS5 username/password to browsers).
_local_bridge_server = None
_local_bridge_lock = threading.Lock()


def _parse_proxy_host_port_auth(proxy_value, proxy_kind="auto"):
    raw = (proxy_value or "").strip()
    if not raw:
        raise ValueError("Пустое значение прокси.")
    kind = (proxy_kind or "auto").lower()
    if "://" not in raw:
        raw = f"socks5://{raw}" if kind == "socks5" else f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        raise ValueError("Неверный формат. Используйте host:port или login:password@host:port")
    user = parsed.username or ""
    pwd = parsed.password or ""
    return parsed.hostname, int(parsed.port), user, pwd


def _socks5_connect_remote(proxy_host, proxy_port, dest_host, dest_port, username, password):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(60)
    s.connect((proxy_host, int(proxy_port)))
    if username or password:
        s.sendall(b"\x05\x01\x02")
    else:
        s.sendall(b"\x05\x01\x00")
    ver_meth = s.recv(2)
    if len(ver_meth) < 2:
        s.close()
        raise OSError("SOCKS5: короткий ответ")
    if ver_meth[1] == 0xFF:
        s.close()
        raise OSError("SOCKS5: метод не принят")
    if ver_meth[1] == 0x02:
        u = (username or "").encode("utf-8")
        p = (password or "").encode("utf-8")
        if len(u) > 255 or len(p) > 255:
            s.close()
            raise OSError("SOCKS5: слишком длинный логин/пароль")
        auth = bytes([1, len(u)]) + u + bytes([len(p)]) + p
        s.sendall(auth)
        auth_resp = s.recv(2)
        if len(auth_resp) < 2 or auth_resp[1] != 0:
            s.close()
            raise OSError("SOCKS5: ошибка авторизации")
    elif ver_meth[1] != 0x00:
        s.close()
        raise OSError("SOCKS5: неожиданный метод")
    host_b = dest_host.encode("utf-8")
    if len(host_b) > 255:
        s.close()
        raise OSError("SOCKS5: слишком длинный host")
    req = b"\x05\x01\x00\x03" + bytes([len(host_b)]) + host_b + struct.pack("!H", int(dest_port))
    s.sendall(req)
    buf = s.recv(4)
    if len(buf) < 4:
        s.close()
        raise OSError("SOCKS5: короткий ответ CONNECT")
    if buf[1] != 0:
        s.close()
        raise OSError(f"SOCKS5: CONNECT отклонён (код {buf[1]})")
    atyp = buf[3]
    if atyp == 1:
        s.recv(6)
    elif atyp == 3:
        ln = s.recv(1)[0]
        s.recv(ln + 2)
    elif atyp == 4:
        s.recv(18)
    else:
        s.close()
        raise OSError("SOCKS5: неизвестный ATYP")
    return s


def _relay_tcp(a, b):
    try:
        while True:
            r, _, e = select.select([a, b], [], [a, b], 120)
            if e:
                break
            if not r:
                break
            for sock in r:
                other = b if sock is a else a
                data = sock.recv(65536)
                if not data:
                    return
                other.sendall(data)
    except OSError:
        pass
    finally:
        try:
            a.close()
        except OSError:
            pass
        try:
            b.close()
        except OSError:
            pass


def _make_local_proxy_handler(proxy_host, proxy_port, username, password):
    ph, pp, u, p = proxy_host, proxy_port, username, password

    class LocalProxyHandler(socketserver.BaseRequestHandler):
        def handle(self):
            client = self.request
            try:
                client.settimeout(120)
                buf = b""
                while b"\r\n\r\n" not in buf and len(buf) < 65536:
                    chunk = client.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                if b"\r\n\r\n" not in buf:
                    return
                header_end = buf.index(b"\r\n\r\n")
                head = buf[:header_end].decode("latin-1", errors="replace")
                rest = buf[header_end + 4 :]
                first = head.split("\r\n")[0].strip()
                parts = first.split()
                if len(parts) < 2:
                    return
                method, target = parts[0].upper(), parts[1]
                if method == "CONNECT":
                    if ":" not in target:
                        client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                        return
                    h, ps = target.rsplit(":", 1)
                    try:
                        port = int(ps)
                    except ValueError:
                        client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                        return
                    try:
                        remote = _socks5_connect_remote(ph, pp, h, port, u, p)
                    except OSError as ex:
                        client.sendall(
                            ("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + str(ex)).encode("utf-8", errors="replace")
                        )
                        return
                    client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    if rest:
                        remote.sendall(rest)
                    _relay_tcp(client, remote)
                    return
                if method in ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"):
                    if not target.startswith("http://") and not target.startswith("https://"):
                        client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                        return
                    sp = urlsplit(target)
                    host = sp.hostname
                    port = sp.port or (443 if sp.scheme == "https" else 80)
                    if not host:
                        client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                        return
                    try:
                        remote = _socks5_connect_remote(ph, pp, host, port, u, p)
                    except OSError as ex:
                        client.sendall(
                            ("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + str(ex)).encode("utf-8", errors="replace")
                        )
                        return
                    path = sp.path or "/"
                    if sp.query:
                        path = path + "?" + sp.query
                    lines = head.split("\r\n")
                    ver = "HTTP/1.1"
                    if len(lines[0].split()) >= 3:
                        ver = lines[0].split()[2]
                    lines[0] = f"{method} {path} {ver}"
                    new_head = "\r\n".join(lines)
                    remote.sendall(new_head.encode("latin-1", errors="replace") + b"\r\n\r\n" + rest)
                    _relay_tcp(client, remote)
                    return
                client.sendall(b"HTTP/1.1 501 Not Implemented\r\n\r\n")
            except Exception:
                pass
            finally:
                try:
                    client.close()
                except OSError:
                    pass

    return LocalProxyHandler


def stop_local_socks_bridge():
    global _local_bridge_server
    with _local_bridge_lock:
        srv = _local_bridge_server
        _local_bridge_server = None
    if srv is not None:
        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            srv.server_close()
        except Exception:
            pass


def start_local_socks_bridge(proxy_host, proxy_port, username, password):
    stop_local_socks_bridge()
    handler = _make_local_proxy_handler(proxy_host, proxy_port, username, password)
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    srv.allow_reuse_address = True
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    global _local_bridge_server
    with _local_bridge_lock:
        _local_bridge_server = srv
    return port


def _normalize_proxy_value(proxy_value, proxy_kind="auto"):
    """
    Normalize user input to a WinINet-compatible ProxyServer value.
    Supports:
    - host:port
    - login:password@host:port
    - http://host:port
    - socks5://host:port
    """
    raw = (proxy_value or "").strip()
    if not raw:
        raise ValueError("Пустое значение прокси.")

    # If no scheme, default to http.
    candidate = raw if "://" in raw else f"http://{raw}"
    parsed = urlparse(candidate)
    if not parsed.hostname or not parsed.port:
        raise ValueError("Неверный формат. Используйте host:port или login:password@host:port")

    host_port = f"{parsed.hostname}:{parsed.port}"
    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        auth = f"{auth}@"

    scheme = (parsed.scheme or "http").lower()
    kind = (proxy_kind or "auto").lower()
    if kind == "socks5":
        scheme = "socks5"
    elif kind == "http":
        scheme = "http"
    if scheme.startswith("socks"):
        # WinINet format for SOCKS proxy.
        return {
            "wininet": f"socks={auth}{host_port}",
            "url": f"socks5://{auth}{host_port}",
            "scheme": "socks",
        }
    return {
        "wininet": f"http={auth}{host_port};https={auth}{host_port}",
        "url": f"http://{auth}{host_port}",
        "scheme": "http",
    }

def enable_system_proxy(proxy_value, proxy_kind="auto"):
    kind = (proxy_kind or "auto").lower()
    if kind == "socks5":
        ph, pp, u, p = _parse_proxy_host_port_auth(proxy_value, "socks5")
        local_port = start_local_socks_bridge(ph, pp, u, p)
        wininet = f"http=127.0.0.1:{local_port};https=127.0.0.1:{local_port}"
        proxy_url = f"http://127.0.0.1:{local_port}"
    else:
        stop_local_socks_bridge()
        normalized = _normalize_proxy_value(proxy_value, proxy_kind=proxy_kind)
        wininet = normalized["wininet"]
        proxy_url = normalized["url"]
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, wininet)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>")
        try:
            winreg.DeleteValue(key, "AutoConfigURL")
        except FileNotFoundError:
            pass
    _refresh_internet_settings()
    _set_user_env("HTTP_PROXY", proxy_url)
    _set_user_env("HTTPS_PROXY", proxy_url)
    _set_user_env("ALL_PROXY", proxy_url)
    _set_user_env("http_proxy", proxy_url)
    _set_user_env("https_proxy", proxy_url)
    _set_user_env("all_proxy", proxy_url)
    _broadcast_env_change()
    if kind == "socks5":
        return f"локальный HTTP {proxy_url} → SOCKS5 {ph}:{pp}"
    return wininet

def disable_system_proxy():
    stop_local_socks_bridge()
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "")
    _refresh_internet_settings()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        _delete_user_env(name)
    _broadcast_env_change()

def close_cursor_processes(log_cb):
    """
    Находит и завершает все процессы Cursor перед сбросом ID.
    Возвращает True, если удалось продолжить выполнение.
    """
    log_cb("Проверяю запущенные процессы Cursor...")
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            log_cb("⚠ Не удалось получить список процессов. Продолжаю выполнение.")
            return True
    except Exception as e:
        log_cb(f"⚠ Ошибка чтения процессов: {e}. Продолжаю выполнение.")
        return True

    cursor_pids = []
    current_pid = os.getpid()
    # Kill only real Cursor IDE processes, not this app.
    cursor_names = {"cursor.exe", "cursor helper.exe"}
    for line in result.stdout.splitlines():
        row = line.strip().strip('"')
        if not row:
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        image_name = parts[0].lower()
        pid = parts[1]
        try:
            pid_int = int(pid)
        except Exception:
            continue

        if pid_int == current_pid:
            continue

        if image_name in cursor_names:
            cursor_pids.append((image_name, pid_int))

    if not cursor_pids:
        log_cb("Процессы Cursor не найдены.")
        return True

    log_cb(f"Найдено процессов Cursor: {len(cursor_pids)}. Завершаю...")
    for image_name, pid in cursor_pids:
        try:
            kill = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if kill.returncode == 0:
                log_cb(f"✓ Завершён: {image_name} (PID {pid})")
            else:
                log_cb(f"⚠ Не удалось завершить {image_name} (PID {pid})")
        except Exception as e:
            log_cb(f"⚠ Ошибка завершения {image_name} (PID {pid}): {e}")

    return True

# ─── POWERSHELL AUTOMATION ─────────────────────────────────────────────────────
def run_cursor_reset(log_cb, done_cb):
    """
    Запускает скрипт сброса Cursor через PowerShell от имени администратора.
    Автоматически отвечает: 2 → yes → yes → Enter.

    Метод: wrapper .ps1 переопределяет global:Read-Host,
    затем запускается через ShellExecute с verb=runas (UAC elevation).
    """
    import tempfile, ctypes, time

    if not close_cursor_processes(log_cb):
        done_cb(False)
        return

    log_cb("Подготовка wrapper-скрипта...")

    # Wrapper PS1: переопределяем Read-Host, скачиваем и запускаем оригинал
    ps1_content = (
        "$ErrorActionPreference = 'Stop'\n"
        "$ProgressPreference    = 'SilentlyContinue'\n"
        "$logPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'cursor_reset_wrapper.log')\n"
        "function Write-Log($msg) {\n"
        "    $line = ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $msg)\n"
        "    Add-Content -Path $logPath -Value $line -Encoding UTF8\n"
        "}\n"
        "Write-Log 'Wrapper started.'\n"
        "\n"
        "# Auto answers queue: 2, yes, yes, (empty=Enter)\n"
        "$script:_q = [System.Collections.Queue]::new()\n"
        'foreach ($a in @("2","yes","yes","")) { $script:_q.Enqueue($a) }\n'
        "\n"
        "function global:Read-Host {\n"
        "    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$P)\n"
        "    $txt = $P -join ' '\n"
        "    if ($txt) { Write-Host $txt }\n"
        "    if ($script:_q.Count -gt 0) {\n"
        "        $ans = $script:_q.Dequeue()\n"
        "        Write-Host \"> $ans\"\n"
        "        return $ans\n"
        "    }\n"
        "    return ''\n"
        "}\n"
        "\n"
        "try {\n"
        "    Write-Host '[*] Downloading script...'\n"
        "    Write-Log 'Downloading remote script...'\n"
        "    $url  = 'https://raw.githubusercontent.com/yuaotian/go-cursor-help/refs/heads/master/scripts/run/cursor_win_id_modifier.ps1'\n"
        "    $code = (Invoke-WebRequest -Uri $url -UseBasicParsing -ErrorAction Stop).Content\n"
        "    Write-Host '[*] Running script...'\n"
        "    Write-Log 'Executing remote script...'\n"
        "    Invoke-Expression $code\n"
        "    Write-Host '[DONE] Completed.'\n"
        "    Write-Log 'Remote script finished successfully.'\n"
        "} catch {\n"
        "    Write-Host '[ERROR] Script failed:' -ForegroundColor Red\n"
        "    Write-Host $_.Exception.Message -ForegroundColor Red\n"
        "    if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed }\n"
        "    Write-Log ('ERROR: ' + $_.Exception.Message)\n"
        "    if ($_.ScriptStackTrace) { Write-Log ('STACK: ' + $_.ScriptStackTrace) }\n"
        "} finally {\n"
        "    Write-Log 'Wrapper finished.'\n"
        "}\n"
        "Write-Host ''\n"
        "Write-Host ('Log saved: ' + $logPath)\n"
    )

    tmp_ps1 = os.path.join(tempfile.gettempdir(), "cursor_autoreset.ps1")

    try:
        # Use BOM so Windows PowerShell 5.1 reads script encoding correctly.
        with open(tmp_ps1, "w", encoding="utf-8-sig") as f:
            f.write(ps1_content)

        log_cb(f"Скрипт записан: {tmp_ps1}")
        log_cb("Запускаю PowerShell от администратора...")
        log_cb("⚠ Примите запрос UAC (если появится).")

        # ShellExecute с verb "runas" — единственный надёжный способ UAC elevation
        # из Python без ctypes. Используем ShellExecuteW напрямую через ctypes.
        ps_args = f'-ExecutionPolicy Bypass -WindowStyle Normal -File "{tmp_ps1}"'

        ret = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # verb — запрашивает права администратора
            "powershell.exe",
            ps_args,
            None,           # directory
            1               # SW_SHOWNORMAL — окно видимо
        )

        if ret <= 32:
            # Коды ≤32 — ошибка
            errors = {
                2: "Файл не найден (powershell.exe)",
                3: "Путь не найден",
                5: "Отказано в доступе / UAC отклонён",
                1223: "Пользователь отменил UAC",
            }
            msg = errors.get(ret, f"Код ошибки ShellExecute: {ret}")
            log_cb(f"✗ {msg}")
            done_cb(False)
            return

        log_cb("✓ PowerShell запущен (видимое окно).")
        log_cb("Автоответы: 2 → yes → yes → Enter")
        log_cb("Ожидаю завершения...")

        # Ждём пока powershell закроется (до 3 минут)
        for i in range(180):
            time.sleep(1)
            try:
                chk = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq powershell.exe", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                running = "powershell.exe" in chk.stdout.lower()
            except Exception:
                running = True

            if i >= 8 and not running:
                break
            if i > 0 and i % 20 == 0:
                log_cb(f"  ... {i} сек")

        log_cb("✓ Скрипт завершён. Перезапустите Cursor.")
        done_cb(True)

    except Exception as e:
        log_cb(f"✗ Неожиданная ошибка: {e}")
        done_cb(False)

# ─── MAIN APP ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cursor Tool")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.window_w = 840
        self.window_h = 950
        self.geometry(f"{self.window_w}x{self.window_h}")
        self.state("zoomed")

        self.mail_path = tk.StringVar(value="")
        self.gen_first  = tk.StringVar()
        self.gen_last   = tk.StringVar()
        self.gen_pass   = tk.StringVar()
        self.gen_email_login = tk.StringVar()
        self.gen_email_pass = tk.StringVar()
        self.verification_code_var = tk.StringVar(value="")
        self.account_password_mode_var = tk.StringVar(value="generated")
        self.custom_account_password_var = tk.StringVar()
        self.bringsms_api_var = tk.StringVar()
        self.bringsms_max_price_var = tk.StringVar()
        self.proxy_var = tk.StringVar()
        self.proxy_type_var = tk.StringVar(value="SOCKS5")
        self.status_var = tk.StringVar(value="Готов к работе")
        self.accounts_gen_reg_count_var = tk.IntVar(value=1)

        _cfg = load_app_config()
        self.account_password_mode_var.set(_cfg.get("account_password_mode") or "generated")
        self.custom_account_password_var.set(_cfg.get("custom_account_password") or "")
        self.bringsms_api_var.set(_cfg.get("bringsms_api_key") or "")
        self.bringsms_max_price_var.set(_cfg.get("bringsms_max_price") or "")

        self._detect_mail_file()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_idletasks()
        self._center()

    def report_callback_exception(self, exc_type, exc_value, exc_tb):
        """Capture Tkinter callback crashes to crash.log."""
        write_crash_log("TKINTER_CALLBACK_EXCEPTION", exc_type, exc_value, exc_tb)
        try:
            messagebox.showerror(
                "Ошибка",
                f"Произошла ошибка. Лог сохранен в:\n{crash_log_path()}"
            )
        except Exception:
            pass

    def _detect_mail_file(self):
        default = Path(data_file_path("mail.txt"))
        if default.exists():
            p = str(default.resolve())
            self.mail_path.set(p)
            self.after(0, lambda path=p: self._report_mail_file_loaded(path))

    def _center(self):
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()

        # Prefer Windows work area (excludes taskbar) to avoid bottom clipping.
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2, 0)
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                work_w = rect.right - rect.left
                work_h = rect.bottom - rect.top
                x = rect.left + max((work_w - w) // 2, 0)
                y = rect.top + max((work_h - h) // 2, 0)
                # Clamp inside work area in case of DPI quirks.
                x = min(max(x, rect.left), max(rect.right - w, rect.left))
                y = min(max(y, rect.top), max(rect.bottom - h, rect.top))
        except Exception:
            pass

        self.geometry(f"+{x}+{y}")

    # ── UI BUILD ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = tk.Frame(self, bg=BG, padx=0, pady=0)
        outer.pack(fill="both", expand=True)

        # ── Header with Logo (Centered) ───────────────────────────────────────
        header_cont = tk.Frame(outer, bg=BG, pady=20)
        header_cont.pack(fill="x")
        
        # Inner frame to hold logo + text, centered
        inner_header = tk.Frame(header_cont, bg=BG)
        inner_header.pack(anchor="center")

        img_path = self._find_banner_image()
        if PIL_AVAILABLE and img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                logo_w, logo_h = 120, 100
                img = img.resize((logo_w, logo_h), Image.LANCZOS)
                self._banner = ImageTk.PhotoImage(img)
                logo_lbl = tk.Label(inner_header, image=self._banner, bg=BG, bd=0)
                logo_lbl.pack(side="left", padx=(0, 20))
            except Exception:
                pass

        header_text = tk.Frame(inner_header, bg=BG)
        header_text.pack(side="left", fill="y")
        
        tk.Label(header_text, text="Cursor Tool", bg=BG, fg=TEXT,
                 font=("Segoe UI", 24, "bold"), justify="left").pack(anchor="w")
        tk.Label(header_text, text="Сброс Cursor ID, аккаунты и управление прокси",
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=(2, 0))

        # ── Main card (2 columns) ─────────────────────────────────────────────
        card = tk.Frame(outer, bg=SURFACE, padx=18, pady=16, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        card.grid_columnconfigure(0, weight=1, uniform="col")
        card.grid_columnconfigure(1, weight=1, uniform="col")
        card.grid_rowconfigure(0, weight=1)

        left_col = tk.Frame(card, bg=SURFACE)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right_col = tk.Frame(card, bg=SURFACE)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Left column
        sec_label(left_col, "ФАЙЛ С ПОЧТАМИ").pack(anchor="w", pady=(0, 6))
        mail_row = tk.Frame(left_col, bg=SURFACE)
        mail_row.pack(fill="x", pady=(0, 14))
        styled_entry(mail_row, textvariable=self.mail_path, width=34).pack(side="left", fill="x", expand=True, padx=(0, 8))
        icon_button(mail_row, "Выбрать файл", self._browse_mail).pack(side="left")

        btn_block = tk.Frame(left_col, bg=SURFACE3, padx=12, pady=12, highlightthickness=1, highlightbackground=BORDER)
        btn_block.pack(fill="x", pady=(0, 12))
        btn_row = tk.Frame(btn_block, bg=SURFACE3)
        btn_row.pack(fill="x")
        big_button(btn_row, "Сбросить Cursor", self._run_cursor_reset, ACCENT).pack(side="left", expand=True, fill="x", padx=(0, 8))
        big_button(btn_row, "Сгенерировать один аккаунт", self._generate_account, "#2d6a4f").pack(side="left", expand=True, fill="x")
        btn_row2 = tk.Frame(btn_block, bg=SURFACE3)
        btn_row2.pack(fill="x", pady=(8, 0))
        big_button(btn_row2, "Сгенерировать все аккаунты из файла", self._generate_all_accounts, "#14532d").pack(fill="x")
        reg_scale_row = tk.Frame(btn_block, bg=SURFACE3)
        reg_scale_row.pack(fill="x", pady=(8, 4))
        tk.Label(
            reg_scale_row,
            text="Аккаунтов (сгенерировать и зарегистрировать, 1–5):",
            bg=SURFACE3,
            fg=TEXT_DIM,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 8))
        tk.Scale(
            reg_scale_row,
            variable=self.accounts_gen_reg_count_var,
            from_=1,
            to=5,
            orient="horizontal",
            length=200,
            showvalue=True,
            resolution=1,
            bg=SURFACE3,
            fg=TEXT,
            highlightthickness=0,
            troughcolor=SURFACE2,
            activebackground=ACCENT,
        ).pack(side="left", fill="x", expand=True)
        btn_row3 = tk.Frame(btn_block, bg=SURFACE3)
        btn_row3.pack(fill="x", pady=(4, 0))
        big_button(btn_row3, "Сгенерировать и зарегистрировать", self._generate_and_register_accounts, "#1d4ed8").pack(fill="x")

        pwd_block = tk.Frame(left_col, bg=SURFACE3, padx=12, pady=12, highlightthickness=1, highlightbackground=BORDER)
        pwd_block.pack(fill="x", pady=(0, 12))
        sec_label(pwd_block, "ПАРОЛЬ АККАУНТА CURSOR").pack(anchor="w", pady=(0, 6))
        pwd_mode_row = tk.Frame(pwd_block, bg=SURFACE3)
        pwd_mode_row.pack(fill="x")
        for txt, val in (
            ("Авто (сгенерировать)", "generated"),
            ("Как у почты", "email"),
            ("Свой пароль", "custom"),
        ):
            tk.Radiobutton(
                pwd_mode_row,
                text=txt,
                value=val,
                variable=self.account_password_mode_var,
                command=self._on_account_password_mode_changed,
                bg=SURFACE3,
                fg=TEXT,
                selectcolor=SURFACE2,
                activebackground=SURFACE3,
                activeforeground=TEXT,
                font=("Segoe UI", 9),
                highlightthickness=0,
                bd=0,
            ).pack(anchor="w", pady=1)
        self.custom_pwd_row = tk.Frame(pwd_block, bg=SURFACE3)
        self.custom_pwd_row.pack(fill="x", pady=(6, 0))
        tk.Label(
            self.custom_pwd_row,
            text="Свой пароль",
            bg=SURFACE3,
            fg=TEXT_DIM,
            font=("Segoe UI", 9),
            width=16,
            anchor="w",
        ).pack(side="left")
        self.custom_account_password_entry = styled_entry(
            self.custom_pwd_row,
            textvariable=self.custom_account_password_var,
            width=28,
            show="•",
        )
        self.custom_account_password_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.custom_account_password_entry.bind("<FocusOut>", lambda e: self._persist_user_settings())

        proxy_block = tk.Frame(left_col, bg=SURFACE3, padx=12, pady=12, highlightthickness=1, highlightbackground=BORDER)
        proxy_block.pack(fill="x", pady=(0, 12))
        sec_label(proxy_block, "ПРОКСИ").pack(anchor="w", pady=(0, 6))
        proxy_row = tk.Frame(proxy_block, bg=SURFACE3)
        proxy_row.pack(fill="x")
        type_row = tk.Frame(proxy_block, bg=SURFACE3)
        type_row.pack(fill="x", pady=(0, 6))
        tk.Label(type_row, text="Тип:", bg=SURFACE3, fg=TEXT_DIM, font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        for txt in ("SOCKS5", "HTTP"):
            tk.Radiobutton(
                type_row,
                text=txt,
                value=txt,
                variable=self.proxy_type_var,
                bg=SURFACE3,
                fg=TEXT,
                selectcolor=SURFACE2,
                activebackground=SURFACE3,
                activeforeground=TEXT,
                font=("Segoe UI", 9),
                highlightthickness=0,
                bd=0
            ).pack(side="left", padx=(0, 10))
        self.proxy_entry = styled_entry(proxy_row, textvariable=self.proxy_var, width=30)
        self.proxy_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.proxy_entry.config(state="normal")
        self.proxy_entry.bind("<<Paste>>", self._paste_into_proxy)
        self.proxy_entry.bind("<Shift-Insert>", self._paste_into_proxy)
        self.proxy_entry.bind("<Button-3>", self._show_proxy_context_menu)
        self.bind_all("<Control-KeyPress>", self._paste_proxy_hotkey, add="+")
        icon_button(proxy_row, "Вкл", self._enable_proxy).pack(side="left", padx=(0, 6))
        icon_button(proxy_row, "Выкл", self._disable_proxy).pack(side="left")
        tk.Label(
            proxy_block,
            text="SOCKS5: Windows не передаёт логин в системный прокси — включается локальный HTTP на 127.0.0.1.\n"
                 "Формат: host:port или login:password@host:port",
            bg=SURFACE3,
            fg=TEXT_MUTED,
            font=("Segoe UI", 8),
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        sec_label(left_col, "ССЫЛКИ").pack(anchor="w", pady=(0, 6))
        links_frame = tk.Frame(left_col, bg=SURFACE3, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
        links_frame.pack(fill="x")
        links = [
            ("Cursor", "https://cursor.com/dashboard/settings"),
            ("Войти в почту Rambler", "https://mail.rambler.ru/"),
            ("BringSMS API / бот", "https://t.me/bringsmsbot"),
            ("Документация BringSMS", "https://doc.bring-sms.store/"),
	    ("Инструкция по CursorTool / GitHub CursorTool", "https://github.com/pr0cr4st1n4t10n/CursorTool"),
            ("Разработчик CursorTool", "https://pr0cr4st1n4t10n.github.io/"),
        ]
        for title, url in links:
            row = tk.Frame(links_frame, bg=SURFACE3)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{title} - ", bg=SURFACE3, fg=TEXT_DIM, font=("Segoe UI", 9, "bold")).pack(side="left")
            lnk = tk.Label(row, text=url, bg=SURFACE3, fg=ACCENT, font=("Segoe UI", 9), cursor="hand2")
            lnk.pack(side="left")
            lnk.bind("<Button-1>", lambda e, u=url: self._open_url(u))
            lnk.bind("<Enter>", lambda e, w=lnk: w.config(fg="#a89fff"))
            lnk.bind("<Leave>", lambda e, w=lnk: w.config(fg=ACCENT))

        # Right column
        sec_label(right_col, "СГЕНЕРИРОВАННЫЕ ДАННЫЕ").pack(anchor="w", pady=(0, 8))
        fields_box = tk.Frame(right_col, bg=SURFACE3, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
        fields_box.pack(fill="x", pady=(0, 12))
        fields = [
            ("Имя", self.gen_first),
            ("Фамилия", self.gen_last),
            ("Пароль аккаунта", self.gen_pass),
            ("Почта (логин)", self.gen_email_login),
            ("Почта (пароль)", self.gen_email_pass),
        ]
        for label, var in fields:
            self._gen_row(fields_box, label, var)

        nl_block = tk.Frame(right_col, bg=SURFACE3, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
        nl_block.pack(fill="x", pady=(0, 12))
        sec_label(nl_block, "ПОЧТА RAMBLER / КОД ПОДТВЕРЖДЕНИЯ").pack(anchor="w", pady=(0, 6))
        tk.Label(
            nl_block,
            text="Код берётся только из писем от Cursor.",
            bg=SURFACE3,
            fg=TEXT_MUTED,
            font=("Segoe UI", 8),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        big_button(
            nl_block,
            "Получить последний код с почты",
            self._fetch_last_code,
            ACCENT2,
        ).pack(fill="x")

        code_row = tk.Frame(nl_block, bg=SURFACE3)
        code_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            code_row,
            text="Код",
            bg=SURFACE3,
            fg=TEXT_DIM,
            font=("Segoe UI", 9),
            width=16,
            anchor="w",
        ).pack(side="left")
        self.verification_code_entry = styled_entry(
            code_row,
            textvariable=self.verification_code_var,
            font=("Consolas", 12),
        )
        self.verification_code_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.verification_code_entry.config(state="readonly", readonlybackground=SURFACE2)
        icon_button(code_row, "Скопировать", self._copy_verification_code_field).pack(side="left")

        bringsms_block = tk.Frame(right_col, bg=SURFACE3, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
        bringsms_block.pack(fill="x", pady=(0, 12))
        sec_label(bringsms_block, "BRINGSMS (ВИРТУАЛЬНЫЙ НОМЕР)").pack(anchor="w", pady=(0, 6))
        tk.Label(
            bringsms_block,
            text="При запросе телефона: покупка номера Any Other (самый дешёвый).",
            bg=SURFACE3,
            fg=TEXT_MUTED,
            font=("Segoe UI", 8),
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        bs_api_row = tk.Frame(bringsms_block, bg=SURFACE3)
        bs_api_row.pack(fill="x", pady=(0, 4))
        tk.Label(bs_api_row, text="API-ключ", bg=SURFACE3, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
        self.bringsms_api_entry = styled_entry(bs_api_row, textvariable=self.bringsms_api_var, width=28, show="•")
        self.bringsms_api_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.bringsms_api_entry.bind("<FocusOut>", lambda e: self._persist_user_settings())
        bs_price_row = tk.Frame(bringsms_block, bg=SURFACE3)
        bs_price_row.pack(fill="x")
        tk.Label(bs_price_row, text="Макс. цена ₽", bg=SURFACE3, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
        self.bringsms_max_price_entry = styled_entry(bs_price_row, textvariable=self.bringsms_max_price_var, width=12)
        self.bringsms_max_price_entry.pack(side="left", padx=(4, 0))
        self.bringsms_max_price_entry.bind("<FocusOut>", lambda e: self._persist_user_settings())
        tk.Label(
            bs_price_row,
            text="пусто = самый дешёвый",
            bg=SURFACE3,
            fg=TEXT_MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

        log_header = tk.Frame(right_col, bg=right_col["bg"])
        log_header.pack(fill="x", pady=(0, 6))
        sec_label(log_header, "ЛОГ").pack(side="left")
        
        tk.Button(log_header, text="📋 Скопировать", bg=ACCENT, fg="#fff",
                  font=("Segoe UI", 8, "bold"), bd=0, padx=10, pady=3,
                  activebackground=ACCENT2, cursor="hand2", relief="flat",
                  command=self._copy_all_logs).pack(side="right")

        log_box = tk.Frame(right_col, bg=SURFACE3, padx=10, pady=10, highlightthickness=1, highlightbackground=BORDER)
        log_box.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_box, height=16, bg=SURFACE2, fg="#b8b8d9",
                                font=("Consolas", 9), bd=0, relief="flat",
                                insertbackground=ACCENT, wrap="word",
                                state="disabled")
        self.log_text.pack(fill="both", expand=True)

        status_bar = tk.Frame(outer, bg="#101014", padx=14, pady=6)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, textvariable=self.status_var, bg="#101014", fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")

        self._on_account_password_mode_changed()

    def _on_account_password_mode_changed(self):
        mode = (self.account_password_mode_var.get() or "generated").strip().lower()
        self.custom_pwd_row.pack_forget()
        if mode == "custom":
            self.custom_pwd_row.pack(fill="x", pady=(6, 0))
        self._persist_user_settings()

    def _find_banner_image(self):
        candidates = [
            resource_path(os.path.join("images", "image.jpg")),
            resource_path(os.path.join("images", "image.png")),
            resource_path(os.path.join("image.jpg")),
            resource_path(os.path.join("image.png")),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def _placeholder_banner(self, parent):
        f = tk.Frame(parent, bg="#1a1a2e", height=120)
        f.pack(fill="x")
        f.pack_propagate(False)
        tk.Label(f, text="CURSOR TOOL", bg="#1a1a2e", fg=ACCENT,
                 font=("Segoe UI", 24, "bold")).pack(expand=True)

    def _gen_row(self, parent, label, var):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=3)

        tk.Label(row, text=label, bg=parent["bg"], fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")

        entry = styled_entry(row, textvariable=var, width=30)
        entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        entry.config(state="readonly", readonlybackground=SURFACE2)

        copy_btn = tk.Button(row, text="⎘", bg=SURFACE2, fg=TEXT_DIM,
                             font=("Consolas", 10), bd=0, padx=8, pady=3,
                             activebackground=BORDER, activeforeground=TEXT,
                             cursor="hand2", relief="flat",
                             command=lambda v=var: self._copy(v.get()))
        copy_btn.pack(side="left")
        copy_btn.bind("<Enter>", lambda e, b=copy_btn: b.config(fg=ACCENT))
        copy_btn.bind("<Leave>", lambda e, b=copy_btn: b.config(fg=TEXT_DIM))

    # ── ACTIONS ───────────────────────────────────────────────────────────────
    def _browse_mail(self):
        path = filedialog.askopenfilename(
            title="Выберите файл с почтами",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self.mail_path.set(path)
            self._report_mail_file_loaded(path)

    def _report_mail_file_loaded(self, path):
        if not path or not os.path.exists(path):
            self.log(f"⚠ Файл с почтами не найден: {path or '(пусто)'}")
            return
        n = count_email_credentials_in_file(path)
        self.log(f"Файл с почтами загружен: прочитано {n} записей (логин:пароль).")

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _generate_and_register_accounts(self):
        try:
            import selenium  # noqa: F401
        except ImportError:
            messagebox.showerror(
                "Нет Selenium",
                "Установите зависимости:\npip install selenium pyperclip undetected-chromedriver\n\n"
                "Нужен браузер по умолчанию в Windows (Edge, Chrome или Firefox). "
                "pyperclip — вставка в поля как вручную (Ctrl+V).",
            )
            return

        try:
            n = int(self.accounts_gen_reg_count_var.get())
        except (TypeError, ValueError):
            n = 1
        n = max(1, min(5, n))

        path = self.mail_path.get().strip()
        if not path:
            messagebox.showwarning(
                "Почты",
                "Укажите файл с почтами — для каждого аккаунта нужна отдельная строка login:password.",
            )
            return
        if not os.path.exists(path):
            messagebox.showwarning("Почты", f"Файл не найден:\n{path}")
            return

        available = count_email_credentials_in_file(path)
        if available < n:
            messagebox.showwarning(
                "Почты",
                f"В файле только {available} записей, а выбрано {n} аккаунтов.\n"
                "Добавьте строки login:password или уменьшите ползунок.",
            )
            return

        pwd_mode = (self.account_password_mode_var.get() or "generated").strip().lower()
        custom_pwd = self.custom_account_password_var.get().strip()
        if pwd_mode == "custom" and not custom_pwd:
            messagebox.showwarning(
                "Пароль аккаунта",
                "Выбран режим «Свой пароль» — введите пароль для регистрации Cursor.",
            )
            return

        bringsms_key = self.bringsms_api_var.get().strip()
        bringsms_max = self.bringsms_max_price_var.get().strip()

        threading.Thread(
            target=self._generate_and_register_accounts_worker,
            args=(n, path, pwd_mode, custom_pwd, bringsms_key, bringsms_max),
            daemon=True,
        ).start()

    def _apply_snap_to_generated_fields(self, snap):
        """Подставить в поля UI данные одного сгенерированного аккаунта (последний из пачки)."""
        self.gen_first.set(snap["first"])
        self.gen_last.set(snap["last"])
        self.gen_pass.set(snap["account_pass"])
        self.gen_email_login.set(snap["email"])
        self.gen_email_pass.set(snap["email_pass"])

    def _commit_registered_account(self, mail_path, snap):
        """После успешной регистрации: удалить почту из файла и сохранить аккаунт."""
        with _FILE_COMMIT_LOCK:
            removed = remove_email_credentials_from_file(mail_path, snap["email"])
            save_account(
                snap["first"],
                snap["last"],
                snap["email"],
                snap["email_pass"],
                snap["account_pass"],
                filepath=data_file_path("accounts.txt"),
            )
        line = format_account_line(snap["email"], snap["email_pass"], snap["account_pass"]).strip()
        if removed:
            self.log(f"✓ Почта {snap['email']} удалена из файла, сохранено в accounts.txt ({line})")
        else:
            self.log(f"✓ Сохранено в accounts.txt ({line}); почта не найдена в файле для удаления")

    def _generate_and_register_accounts_worker(self, n, path, pwd_mode, custom_pwd, bringsms_key, bringsms_max):
        """Фон: подготовить данные, зарегистрировать; файлы меняются только после успеха."""
        creds_list = list_email_credentials_from_file(path)[:n]
        if not creds_list:
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Генерация",
                    "Не удалось прочитать почты из файла.",
                ),
            )
            return

        snaps = []
        for idx, (email_login, email_password) in enumerate(creds_list):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            pwd = resolve_account_password(pwd_mode, email_password, custom_pwd)
            snap = {
                "first": first,
                "last": last,
                "email": email_login,
                "email_pass": email_password,
                "account_pass": pwd,
                "bringsms_api": bringsms_key,
                "bringsms_max_price": bringsms_max,
            }
            snaps.append(snap)
            self.log(f"✓ [{idx + 1}/{n}] Подготовлен аккаунт: {first} {last} | {email_login}")

        if not snaps:
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Генерация",
                    "Не удалось сгенерировать ни одного аккаунта (нет почт в файле).",
                ),
            )
            return

        last_snap = snaps[-1]
        self.after(0, lambda s=last_snap: self._apply_snap_to_generated_fields(s))

        self.log(f"Запуск регистрации в браузере для {len(snaps)} аккаунт(ов)…")

        if len(snaps) == 1:
            def _run_single():
                ok = self._register_with_generated_data_worker(
                    snaps[0], instance_id=0, parallel_total=1
                )
                if ok:
                    self._commit_registered_account(path, snaps[0])
                else:
                    self.log(f"✗ Регистрация не удалась для {snaps[0]['email']} — почта остаётся в файле.")

            threading.Thread(target=_run_single, daemon=True).start()
        else:
            threading.Thread(
                target=self._register_parallel_supervisor,
                args=(snaps, path),
                daemon=True,
            ).start()

    def _register_parallel_supervisor(self, snaps, mail_path):
        """Несколько окон с разными snap; общий снимок буфера до/после."""
        if not snaps:
            return
        n = len(snaps)
        self.log(f"Регистрация: параллельно {n} окон (по одному на аккаунт)…")

        clip_snapshot = None
        try:
            import pyperclip
            with _CLIPBOARD_LOCK:
                try:
                    clip_snapshot = pyperclip.paste()
                except Exception:
                    clip_snapshot = None
        except ImportError:
            pass

        threads = []

        def _run_reg(snap, idx, total):
            time.sleep(0.28 * idx + random.uniform(0, 0.14))
            ok = self._register_with_generated_data_worker(
                snap, instance_id=idx, parallel_total=total
            )
            if ok:
                self._commit_registered_account(mail_path, snap)
            else:
                self.log(f"✗ Регистрация не удалась для {snap['email']} — почта остаётся в файле.")

        for i, snap in enumerate(snaps):
            t = threading.Thread(
                target=_run_reg,
                args=(snap, i, n),
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        if clip_snapshot is not None:
            try:
                import pyperclip
                with _CLIPBOARD_LOCK:
                    pyperclip.copy(clip_snapshot)
            except Exception:
                pass

    def _register_with_generated_data_worker(self, snap, instance_id=0, parallel_total=1):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        signup_url = "https://authenticator.cursor.sh/sign-up"
        first = snap["first"]
        last = snap["last"]
        email = snap["email"]
        email_pass = snap["email_pass"]
        account_pass = snap["account_pass"]

        owns_clipboard_restore = parallel_total == 1
        success = False
        clip_snapshot = None
        if owns_clipboard_restore:
            try:
                import pyperclip
                with _CLIPBOARD_LOCK:
                    try:
                        clip_snapshot = pyperclip.paste()
                    except Exception:
                        clip_snapshot = None
            except ImportError:
                pass

        log_reg = (
            (lambda m: self.log(f"[окно {instance_id + 1}/{parallel_total}] {m}"))
            if parallel_total > 1
            else self.log
        )
        # Всегда отдельный временный профиль — не смешивать с основным Chrome и не дублировать куки между регистрациями.
        profile_idx = instance_id

        def _fill_first_matching(locators, value, per=6):
            for by, sel in locators:
                try:
                    el = WebDriverWait(driver, per).until(EC.visibility_of_element_located((by, sel)))
                    if el.is_displayed():
                        _selenium_type_human(driver, el, value, fast=True)
                        time.sleep(random.uniform(0.14, 0.32))
                        return True
                except TimeoutException:
                    continue
            return False

        def _switch_latest_tab():
            handles = driver.window_handles
            if len(handles) > 1:
                driver.switch_to.window(handles[-1])

        def _find_otp_single():
            for by, sel in (
                (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
                (By.CSS_SELECTOR, "input[inputmode='numeric']"),
                (By.XPATH, "//input[contains(@placeholder,'код') or contains(@placeholder,'Код') or contains(@placeholder,'code') or contains(@placeholder,'Code')]"),
            ):
                for el in driver.find_elements(by, sel):
                    try:
                        t = (el.get_attribute("type") or "").lower()
                        if t in ("password", "email", "hidden"):
                            continue
                        if el.is_displayed() and el.get_attribute("maxlength") != "1":
                            return el
                    except Exception:
                        continue
            return None

        def _find_otp_multi():
            els = driver.find_elements(By.CSS_SELECTOR, "input[inputmode='numeric'][maxlength='1']")
            vis = [e for e in els if e.is_displayed()]
            return vis if len(vis) >= 4 else None

        driver = None
        try:
            driver = selenium_create_registration_driver(log_reg, instance_index=profile_idx)
            selenium_apply_window_layout(driver, instance_id, parallel_total)
            time.sleep(random.uniform(0.08, 0.22) * instance_id)
            log_reg(
                "Регистрация: заполнение полей (имя, фамилия, почта)..."
            )
            log_reg(f"Регистрация: открываю {signup_url}")
            driver.get(signup_url)
            time.sleep(random.uniform(0.45, 0.95))

            first_locs = [
                (By.CSS_SELECTOR, "input[autocomplete='given-name']"),
                (By.CSS_SELECTOR, "input[name='firstName']"),
                (By.CSS_SELECTOR, "input[name='first_name']"),
                (By.XPATH, "//label[contains(.,'Ваше имя')]//following::input[1]"),
                (By.XPATH, "//label[contains(.,'имя')][not(contains(.,'фамил'))]//following::input[1]"),
            ]
            last_locs = [
                (By.CSS_SELECTOR, "input[autocomplete='family-name']"),
                (By.CSS_SELECTOR, "input[name='lastName']"),
                (By.CSS_SELECTOR, "input[name='last_name']"),
                (By.XPATH, "//label[contains(.,'фамилия') or contains(.,'Фамилия')]//following::input[1]"),
            ]
            email_locs = [
                (By.CSS_SELECTOR, "input[autocomplete='email']"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.XPATH, "//label[contains(.,'почт') or contains(.,'Почт') or contains(.,'email') or contains(.,'Email')]//following::input[1]"),
            ]

            if not _fill_first_matching(first_locs, first):
                raise TimeoutException("Не найдено поле «Ваше имя» на странице регистрации.")
            if not _fill_first_matching(last_locs, last):
                raise TimeoutException("Не найдено поле «Ваша фамилия».")
            if not _fill_first_matching(email_locs, email):
                raise TimeoutException("Не найдено поле электронной почты.")

            submit_locs = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(.,'Continue')]"),
                (By.XPATH, "//button[contains(.,'Продолжить')]"),
                (By.XPATH, "//button[contains(.,'Sign up')]"),
                (By.XPATH, "//button[contains(.,'Далее')]"),
            ]
            if not _selenium_click_first(driver, submit_locs, timeout_each=12, humanize=True):
                log_reg("⚠ Регистрация: не нашёл кнопку отправки формы — нажмите вручную в браузере.")

            log_reg(
                "Регистрация: если появилась капча — решите её; жду поле пароля аккаунта (до 5 мин)…"
            )
            self.after(0, lambda: self.status_var.set("Капча/пароль: решите капчу при необходимости…"))
            try:
                WebDriverWait(driver, 300).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                )
            except TimeoutException:
                raise TimeoutException("Не появилось поле пароля (возможна капча или другой экран).") from None

            time.sleep(random.uniform(0.22, 0.5))
            _switch_latest_tab()
            pwd_inputs = [e for e in driver.find_elements(By.CSS_SELECTOR, "input[type='password']") if e.is_displayed()]
            if not pwd_inputs:
                raise TimeoutException("Поля пароля не видны.")
            for inp in pwd_inputs:
                _selenium_type_human(driver, inp, account_pass, fast=True)
                time.sleep(random.uniform(0.1, 0.26))

            if not _selenium_click_first(driver, submit_locs, timeout_each=10, humanize=True):
                log_reg("⚠ Регистрация: нажмите кнопку продолжения после пароля вручную.")

            time.sleep(random.uniform(0.4, 0.85))
            _switch_latest_tab()

            log_reg("Регистрация: опрашиваю Rambler и жду письмо от Cursor (до ~4 мин)…")
            self.after(0, lambda: self.status_var.set("Запрос кода с почты…"))

            code = None
            deadline = time.time() + 240
            otp_single = None
            otp_multi = None
            while time.time() < deadline:
                try:
                    _data, code_try, meta, _n, err = fetch_verification_code_best_effort(
                        email, email_pass
                    )
                    if err:
                        pass
                    elif code_try:
                        code = code_try
                        log_reg(f"Регистрация: код из письма Cursor: {code}" + (f" ({meta})" if meta else ""))
                        self.after(0, lambda c=code: self._set_verification_code_field(c))
                except Exception as ex:
                    log_reg(f"⚠ Запрос кода (Rambler): {ex}")

                otp_multi = _find_otp_multi()
                otp_single = _find_otp_single() if not otp_multi else None
                if code and (otp_single or otp_multi):
                    break
                if not code:
                    self.after(
                        0,
                        lambda: self.status_var.set("Жду письмо с кодом и поле ввода на странице…"),
                    )
                time.sleep(4)

            if not code:
                raise TimeoutException(
                    "Код из письма Cursor не получен за отведённое время — проверьте ящик и пароль почты."
                )

            wait_otp_deadline = time.time() + 90
            while time.time() < wait_otp_deadline and not otp_single and not otp_multi:
                otp_multi = _find_otp_multi()
                otp_single = _find_otp_single() if not otp_multi else None
                time.sleep(1)

            if otp_multi:
                raw = (code or "").strip()
                log_reg("Регистрация: ввод кода в многоячеечное поле (6 цифр)...")
                # Вставляем код целиком в первую ячейку — большинство OTP-полей распределяют его сами.
                # Это надёжнее и быстрее, чем ввод по одной цифре.
                _selenium_paste_human(driver, otp_multi[0], raw, quick=True)
                time.sleep(random.uniform(0.5, 0.8))
                log_reg("Регистрация: код вставлен в первую ячейку.")
            elif otp_single:
                _selenium_paste_human(driver, otp_single, code, quick=True)
                log_reg("Регистрация: код введён в одиночное поле.")
            else:
                raise TimeoutException(
                    "Код получен, но поле для ввода кода на странице не найдено. Введите код вручную."
                )

            self.after(0, lambda: self.status_var.set("Код e-mail введён в браузер"))
            time.sleep(random.uniform(1.2, 2.4))
            _switch_latest_tab()

            bringsms_key = (snap.get("bringsms_api") or "").strip()
            bringsms_max = snap.get("bringsms_max_price") or ""
            phone_cc, phone_local = _selenium_wait_phone_fields(driver, timeout=25)
            if phone_cc and phone_local:
                if not bringsms_key:
                    raise TimeoutException(
                        "На странице запрошен телефон, но не указан API-ключ BringSMS."
                    )
                log_reg("Регистрация: требуется телефон — покупка номера через BringSMS (Any Other)…")
                self.after(0, lambda: self.status_var.set("Покупка виртуального номера BringSMS…"))
                activation_id = None
                try:
                    activation_id, _phone_raw, _country_id, dial, local = bringsms_buy_cheapest_ot(
                        bringsms_key, bringsms_max, log_cb=log_reg
                    )
                    log_reg(f"BringSMS: номер {dial}{local} (активация {activation_id})")
                    _selenium_paste_human(driver, phone_cc, dial, quick=True)
                    time.sleep(random.uniform(0.2, 0.45))
                    _selenium_paste_human(driver, phone_local, local, quick=True)
                    time.sleep(random.uniform(0.25, 0.5))
                    if not _selenium_click_first(driver, submit_locs, timeout_each=12, humanize=True):
                        log_reg("⚠ Регистрация: нажмите кнопку продолжения после телефона вручную.")
                    time.sleep(random.uniform(1.0, 2.0))
                    _switch_latest_tab()

                    log_reg("BringSMS: ожидание SMS-кода (до ~5 мин)…")
                    self.after(0, lambda: self.status_var.set("Ожидание SMS-кода…"))
                    sms_code = bringsms_poll_sms_code(
                        bringsms_key, activation_id, timeout=300, log_cb=log_reg
                    )
                    log_reg(f"BringSMS: SMS-код: {sms_code}")
                    self.after(0, lambda c=sms_code: self._set_verification_code_field(c))

                    sms_otp_single = None
                    sms_otp_multi = None
                    sms_deadline = time.time() + 90
                    while time.time() < sms_deadline:
                        sms_otp_single, sms_otp_multi = _selenium_find_otp_fields(driver)
                        if sms_otp_single or sms_otp_multi:
                            break
                        time.sleep(1)

                    if sms_otp_multi:
                        _selenium_paste_human(driver, sms_otp_multi[0], sms_code.strip(), quick=True)
                        log_reg("Регистрация: SMS-код вставлен в многоячеечное поле.")
                    elif sms_otp_single:
                        _selenium_paste_human(driver, sms_otp_single, sms_code, quick=True)
                        log_reg("Регистрация: SMS-код введён в одиночное поле.")
                    else:
                        raise TimeoutException(
                            "SMS-код получен, но поле ввода на странице не найдено. Введите вручную."
                        )

                    try:
                        bringsms_set_status(bringsms_key, activation_id, 6)
                        log_reg("BringSMS: активация завершена.")
                    except Exception as ex:
                        log_reg(f"⚠ BringSMS setStatus(6): {ex}")
                    self.after(0, lambda: self.status_var.set("SMS-код введён в браузер"))
                except Exception:
                    if activation_id:
                        try:
                            bringsms_set_status(bringsms_key, activation_id, 8)
                            log_reg("BringSMS: активация отменена (возврат средств при отсутствии SMS).")
                        except Exception:
                            pass
                    raise
            else:
                log_reg("Регистрация: запрос телефона не появился — продолжаем без BringSMS.")
                self.after(0, lambda: self.status_var.set("Регистрация: телефон не требуется"))

            log_reg("Регистрация: проверяю успешное завершение…")
            self.after(0, lambda: self.status_var.set("Проверка регистрации…"))
            if not _selenium_wait_registration_success(driver, timeout=120):
                raise TimeoutException("Не удалось подтвердить успешную регистрацию.")
            log_reg("✓ Регистрация успешно завершена.")
            self.after(0, lambda: self.status_var.set("Регистрация завершена"))
            success = True
        except TimeoutException as e:
            msg = str(e) or "Таймаут ожидания на странице."
            log_reg(f"✗ Регистрация: {msg}")
            self.after(0, lambda m=msg: messagebox.showerror("Регистрация", m))
        except Exception as e:
            msg = str(e) or type(e).__name__
            log_reg(f"✗ Регистрация: {msg}")
            self.after(0, lambda m=msg: messagebox.showerror("Регистрация", m))
        finally:
            if owns_clipboard_restore and clip_snapshot is not None:
                try:
                    import pyperclip
                    with _CLIPBOARD_LOCK:
                        pyperclip.copy(clip_snapshot)
                except Exception:
                    pass
        return success

    def _copy(self, text):
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.log(f"Скопировано: {text[:40]}...")
            self.status_var.set("Скопировано в буфер обмена")

    def _paste_into_proxy(self, _event=None):
        try:
            data = self.clipboard_get()
        except Exception:
            return "break"
        if not data:
            return "break"
        target = self.focus_get()
        if target is self.proxy_entry:
            try:
                sel_first = target.index("sel.first")
                sel_last = target.index("sel.last")
                target.delete(sel_first, sel_last)
                target.insert(sel_first, data)
            except Exception:
                target.insert("insert", data)
        else:
            self.proxy_entry.insert("insert", data)
        return "break"

    def _paste_proxy_hotkey(self, event):
        if self.focus_get() is not self.proxy_entry:
            return None
        # Works across keyboard layouts (EN/RU/etc):
        # detect Ctrl + physical "V" key (VK code 86 on Windows) or char fallback.
        ch = (event.char or "").lower()
        if event.keycode == 86 or ch in {"v", "м"}:
            return self._paste_into_proxy(event)
        return None

    def _show_proxy_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=SURFACE2, fg=TEXT, activebackground=BORDER, activeforeground=TEXT)
        menu.add_command(label="Вставить", command=lambda: self._paste_into_proxy())
        menu.add_separator()
        menu.add_command(label="Очистить", command=lambda: self.proxy_var.set(""))
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_all_logs(self):
        try:
            self.log_text.config(state="normal")
            content = self.log_text.get("1.0", "end").strip()
            self.log_text.config(state="disabled")

            if not content:
                messagebox.showinfo("Логи", "Лог пустой")
                return

            self.clipboard_clear()
            self.clipboard_append(content)
            messagebox.showinfo("Успешно", "Все логи скопированы в буфер обмена!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скопировать логи:\n{e}")

    def _log(self, msg):
        self.log_text.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def log(self, msg):
        self.after(0, self._log, msg)

    def _show_toast(self, message, duration_ms=3200, bg="#1f2937", fg="#e8e8f0"):
        """
        Неблокирующее уведомление поверх основного окна.
        Не мешает работе с приложением и исчезает автоматически.
        """
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=bg)

        # Делаем окно компактным и визуально отделяем от фона.
        frame = tk.Frame(toast, bg=bg, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text=message,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 9),
            padx=12,
            pady=8,
            justify="left",
            anchor="w",
        ).pack(fill="both", expand=True)

        toast.update_idletasks()
        # Размещаем в правом нижнем углу основного окна.
        x = self.winfo_rootx() + self.winfo_width() - toast.winfo_reqwidth() - 16
        y = self.winfo_rooty() + self.winfo_height() - toast.winfo_reqheight() - 16
        toast.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        toast.after(duration_ms, toast.destroy)

    def _run_cursor_reset(self):
        self.log("─" * 40)
        self.log("Запуск сброса Cursor ID...")
        self.status_var.set("Выполняется сброс Cursor ID...")

        def done(ok):
            # Any Tk/UI work must run on the main thread.
            self.after(0, self._on_cursor_reset_done, ok)

        t = threading.Thread(
            target=run_cursor_reset,
            args=(self.log, done),
            daemon=True
        )
        t.start()

    def _on_cursor_reset_done(self, ok):
        self.log("─" * 40)
        if ok:
            self.log("✓ Готово!")
            self.status_var.set("Сброс Cursor ID завершён")
            self._show_toast("Cursor успешно сброшен", 3000, "#14532d", "#dcfce7")
        else:
            self.log("✗ Завершено с ошибкой.")
            self.status_var.set("Ошибка при сбросе Cursor ID")

    def _generate_account(self):
        path = self.mail_path.get().strip()
        email_login = ""
        email_password = ""
        if path and os.path.exists(path):
            creds = pop_email_credentials_from_file(path)
            if creds:
                email_login, email_password = creds
            else:
                self.log("⚠ В файле почт не найдено корректных строк login:password")
        elif path:
            self.log(f"⚠ Файл не найден: {path}. Почта оставлена пустой.")

        self._apply_generated_account(email_login, email_password, show_toast=True)

    def _apply_generated_account(self, email_login, email_password, show_toast=False):
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        pwd_mode = (self.account_password_mode_var.get() or "generated").strip().lower()
        custom_pwd = self.custom_account_password_var.get().strip()
        if pwd_mode == "custom" and not custom_pwd:
            messagebox.showwarning(
                "Пароль аккаунта",
                "Выбран режим «Свой пароль» — введите пароль в поле ниже.",
            )
            return
        pwd = resolve_account_password(pwd_mode, email_password, custom_pwd)

        self.gen_first.set(first)
        self.gen_last.set(last)
        self.gen_pass.set(pwd)
        self.gen_email_login.set(email_login)
        self.gen_email_pass.set(email_password)

        save_account(first, last, email_login, email_password, pwd, filepath=data_file_path("accounts.txt"))
        mail_info = email_login if email_login else "без почты"
        self.log(f"✓ Аккаунт создан: {first} {last} | {mail_info}")
        self.log(f"  Сохранено в accounts.txt ({format_account_line(email_login, email_password, pwd).strip()})")
        self.status_var.set(f"Аккаунт создан: {first} {last}")
        if show_toast:
            self._show_toast(
                "Аккаунт сгенерирован.\nДанные сохранены в accounts.txt в корневой папке.",
                duration_ms=4200,
                bg="#1e3a8a",
                fg="#dbeafe",
            )

    def _generate_all_accounts(self):
        path = self.mail_path.get().strip()
        if not path:
            messagebox.showwarning("Почты", "Укажите файл с почтами (кнопка «Выбрать файл»).")
            return
        if not os.path.exists(path):
            messagebox.showwarning("Почты", f"Файл не найден:\n{path}")
            return

        initial = count_email_credentials_in_file(path)
        if initial == 0:
            self.log("⚠ В файле нет корректных строк login:password — нечего генерировать.")
            messagebox.showinfo("Почты", "В файле нет строк формата логин:пароль.")
            return

        self.log(f"─ Массовая генерация: в файле {initial} записей.")
        total = 0
        while True:
            creds = pop_email_credentials_from_file(path)
            if not creds:
                break
            email_login, email_password = creds
            self._apply_generated_account(email_login, email_password, show_toast=False)
            total += 1

        self.log(f"─ Готово: создано аккаунтов: {total} (максимум из файла).")
        self.status_var.set(f"Создано аккаунтов: {total}")
        self._show_toast(
            f"Создано аккаунтов: {total}.\nДанные в accounts.txt.",
            duration_ms=4800,
            bg="#14532d",
            fg="#dcfce7",
        )

    def _enable_proxy(self):
        proxy = self.proxy_var.get().strip()
        if not proxy:
            messagebox.showwarning("Прокси", "Введите прокси в формате host:port")
            return
        try:
            proxy_kind = self.proxy_type_var.get().strip().lower()
            applied = enable_system_proxy(proxy, proxy_kind=proxy_kind)
            self.log(f"✓ Прокси включен: {applied}")
            self.status_var.set("Прокси включен")
            self._show_toast("Прокси успешно включен", 2800, "#1e3a8a", "#dbeafe")
        except Exception as e:
            self.log(f"✗ Ошибка включения прокси: {e}")
            self.status_var.set("Ошибка включения прокси")
            messagebox.showerror("Прокси", f"Не удалось включить прокси:\n{e}")

    def _disable_proxy(self):
        try:
            disable_system_proxy()
            self.log("✓ Прокси отключен")
            self.status_var.set("Прокси отключен")
            self._show_toast("Прокси отключен", 2600, "#14532d", "#dcfce7")
        except Exception as e:
            self.log(f"✗ Ошибка отключения прокси: {e}")
            self.status_var.set("Ошибка отключения прокси")
            messagebox.showerror("Прокси", f"Не удалось отключить прокси:\n{e}")

    def _on_close(self):
        self._persist_user_settings()
        self.destroy()

    def _persist_user_settings(self):
        save_app_config_values(
            account_password_mode=self.account_password_mode_var.get(),
            custom_account_password=self.custom_account_password_var.get(),
            bringsms_api_key=self.bringsms_api_var.get(),
            bringsms_max_price=self.bringsms_max_price_var.get(),
        )

    def _set_verification_code_field(self, text):
        self.verification_code_var.set(text or "")
        ent = self.verification_code_entry
        ent.config(state="normal")
        ent.delete(0, "end")
        if text:
            ent.insert(0, text)
        ent.config(state="readonly")

    def _copy_verification_code_field(self):
        t = (self.verification_code_var.get() or "").strip()
        if not t:
            self.status_var.set("Поле кода пустое")
            return
        self.clipboard_clear()
        self.clipboard_append(t)
        self.log(f"Скопирован код: {t}")
        self.status_var.set("Код скопирован в буфер обмена")

    def _fetch_last_code(self):
        email = self.gen_email_login.get().strip()
        pwd = self.gen_email_pass.get().strip()
        if not email or not pwd:
            messagebox.showwarning(
                "Rambler",
                "Нет данных почты.\nСначала сгенерируйте аккаунт или заполните поля «Почта (логин)» и «Почта (пароль)».",
            )
            return
        self._set_verification_code_field("")
        self.log("Запрос писем через IMAP Rambler (только от Cursor)…")
        self.status_var.set("Загрузка почты Rambler…")

        def work():
            code = meta = None
            n_letters = 0
            err = None
            try:
                _data, code, meta, n_letters, err = fetch_verification_code_best_effort(email, pwd)
            except Exception as e:
                err = str(e)
            self.after(
                0,
                lambda c=code, m=meta, n=n_letters, er=err: self._on_fetch_code_done(c, m, n, er),
            )

        threading.Thread(target=work, daemon=True).start()

    def _on_fetch_code_done(self, code, meta, n_letters, err):
        self._persist_user_settings()
        if err:
            self._set_verification_code_field("")
            self.log(f"✗ Rambler: {err}")
            self.status_var.set("Ошибка Rambler")
            messagebox.showerror("Rambler", f"Не удалось получить письма:\n{err}")
            return
        self.log(f"✓ Rambler: писем от Cursor: {n_letters}")
        if n_letters == 0:
            self._set_verification_code_field("")
            self.log("  Писем от Cursor пока нет.")
            self.status_var.set("Нет писем от Cursor")
            messagebox.showinfo("Rambler", "В ящике нет писем от Cursor.")
            return
        if code:
            self._set_verification_code_field(code)
            self.clipboard_clear()
            self.clipboard_append(code)
            self.log(f"✓ Код из письма Cursor: {code}")
            if meta:
                self.log(f"  ({meta})")
            self.status_var.set("Код получен (также в буфере обмена)")
            self._show_toast(
                f"Код: {code}\nСкопирован в буфер; можно скопировать снова кнопкой.",
                3800,
                "#14532d",
                "#dcfce7",
            )
        else:
            self._set_verification_code_field("")
            self.log("⚠ В письме Cursor не удалось распознать код автоматически.")
            if meta:
                self.log(f"  Письмо: {meta}")
            self.status_var.set("Код в письме не найден")
            messagebox.showinfo(
                "Rambler",
                "Письмо от Cursor найдено, но код не распознан автоматически.\n"
                "Откройте почту на сайте или проверьте текст письма вручную.",
            )

# ─── WIDGET HELPERS ────────────────────────────────────────────────────────────
def sec_label(parent, text):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=TEXT_MUTED,
                    font=("Segoe UI", 8, "bold"), anchor="w")

def sep(parent):
    return tk.Frame(parent, bg=BORDER, height=1)

def styled_entry(parent, **kw):
    opts = {
        "bg": SURFACE2,
        "fg": TEXT,
        "font": ("Segoe UI", 10),
        "bd": 0,
        "relief": "flat",
        "insertbackground": ACCENT,
        "highlightthickness": 1,
        "highlightcolor": ACCENT,
        "highlightbackground": BORDER,
        "disabledbackground": SURFACE2,
        "disabledforeground": TEXT_DIM,
        "readonlybackground": SURFACE2,
    }
    opts.update(kw)
    return tk.Entry(parent, **opts)

def icon_button(parent, text, cmd):
    b = tk.Button(parent, text=text, bg=SURFACE2, fg=TEXT,
                  font=("Segoe UI", 9), bd=0, padx=12, pady=7,
                  activebackground=BORDER, activeforeground=TEXT,
                  cursor="hand2", relief="flat", command=cmd)
    b.bind("<Enter>", lambda e: b.config(bg=BORDER))
    b.bind("<Leave>", lambda e: b.config(bg=SURFACE2))
    return b

def big_button(parent, text, cmd, color):
    b = tk.Button(parent, text=text, bg=color, fg="#fff",
                  font=("Segoe UI", 10, "bold"), bd=0, padx=16, pady=11,
                  activebackground=color, activeforeground="#fff",
                  cursor="hand2", relief="flat", command=cmd)
    b.bind("<Enter>", lambda e: b.config(bg=_darken(color)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b

def _darken(hex_color, factor=0.8):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"

# ─── ENTRY ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.excepthook = _global_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook
    app = App()
    app.mainloop()
