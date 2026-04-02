import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import random
import string
import subprocess
import threading
import json
import ctypes
import traceback
import winreg
import socket
import struct
import select
import socketserver
from urllib.parse import urlparse, urlsplit
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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

def count_email_credentials_in_file(path):
    """Count valid login/password lines (read-only, does not modify the file)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        n = 0
        for line in lines:
            if not line:
                continue
            delim = None
            for d in [":", ";", "|", ",", "\t"]:
                if d in line:
                    delim = d
                    break
            if not delim:
                continue
            left, right = line.split(delim, 1)
            login = left.strip()
            password = right.strip()
            if login and password:
                n += 1
        return n
    except Exception:
        return 0

def pop_email_credentials_from_file(path):
    """Read first login/password from file, remove it, return tuple or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        parsed = []
        for line in lines:
            if not line:
                continue
            delim = None
            for d in [":", ";", "|", ",", "\t"]:
                if d in line:
                    delim = d
                    break
            if not delim:
                continue
            left, right = line.split(delim, 1)
            login = left.strip()
            password = right.strip()
            if login and password:
                parsed.append((line, login, password))

        if not parsed:
            return None

        first_line, login, password = parsed[0]
        rest = []
        removed = False
        for line in lines:
            if not removed and line == first_line:
                removed = True
                continue
            rest.append(line)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rest) + ("\n" if rest else ""))
        return login, password
    except Exception:
        return None

def save_account(first, last, email_login, email_password, account_password, filepath="accounts.txt"):
    entry = (
        f"Имя: {first}\n"
        f"Фамилия: {last}\n"
        f"Почта (логин): {email_login}\n"
        f"Почта (пароль): {email_password}\n"
        f"Пароль аккаунта: {account_password}\n"
        f"{'─' * 38}\n"
    )
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry)

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
        self.proxy_var = tk.StringVar()
        self.proxy_type_var = tk.StringVar(value="SOCKS5")
        self.status_var = tk.StringVar(value="Готов к работе")

        self._detect_mail_file()
        self._build_ui()
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

        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(outer, bg=BG, padx=22, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="Cursor Tool", bg=BG, fg=TEXT,
                 font=("Segoe UI", 19, "bold"), justify="center").pack(anchor="center")
        tk.Label(header, text="Сброс Cursor ID, аккаунты и управление прокси",
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 10), justify="center").pack(anchor="center", pady=(2, 0))

        # ── Banner image ──────────────────────────────────────────────────────
        img_path = self._find_banner_image()
        if PIL_AVAILABLE and img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                banner_w = max(self.window_w - 120, 700)
                img = img.resize((banner_w, 220), Image.LANCZOS)
                self._banner = ImageTk.PhotoImage(img)
                banner_lbl = tk.Label(outer, image=self._banner, bg=BG, bd=0)
                banner_lbl.pack(pady=(0, 2))
            except Exception:
                self._placeholder_banner(outer)
        else:
            self._placeholder_banner(outer)

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
            ("Cursor", "https://cursor.com/"),
            ("Удобная почта", "https://notletters.com/email/login"),
            ("Создатель CursorTools", "https://pr0cr4st1n4t10n.github.io/"),
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

        sec_label(right_col, "ЛОГ").pack(anchor="w", pady=(0, 6))
        log_box = tk.Frame(right_col, bg=SURFACE3, padx=10, pady=10, highlightthickness=1, highlightbackground=BORDER)
        log_box.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_box, height=16, bg=SURFACE2, fg="#b8b8d9",
                                font=("Consolas", 8), bd=0, relief="flat",
                                insertbackground=ACCENT, wrap="word",
                                state="disabled")
        self.log_text.pack(fill="both", expand=True)

        status_bar = tk.Frame(outer, bg="#101014", padx=14, pady=6)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, textvariable=self.status_var, bg="#101014", fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")

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

    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
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
        pwd   = generate_password()

        self.gen_first.set(first)
        self.gen_last.set(last)
        self.gen_pass.set(pwd)
        self.gen_email_login.set(email_login)
        self.gen_email_pass.set(email_password)

        save_account(first, last, email_login, email_password, pwd, filepath=data_file_path("accounts.txt"))
        mail_info = email_login if email_login else "без почты"
        self.log(f"✓ Аккаунт создан: {first} {last} | {mail_info}")
        self.log(f"  Сохранено в accounts.txt")
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

# ─── WIDGET HELPERS ────────────────────────────────────────────────────────────
def sec_label(parent, text):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=TEXT_MUTED,
                    font=("Segoe UI", 8, "bold"), anchor="w")

def sep(parent):
    return tk.Frame(parent, bg=BORDER, height=1)

def styled_entry(parent, **kw):
    e = tk.Entry(parent, bg=SURFACE2, fg=TEXT, font=("Segoe UI", 10),
                 bd=0, relief="flat", insertbackground=ACCENT,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER,
                 disabledbackground=SURFACE2,
                 disabledforeground=TEXT_DIM,
                 readonlybackground=SURFACE2,
                 **kw)
    return e

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
