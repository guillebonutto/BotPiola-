import imaplib
import email
from email.header import decode_header
import json
import os
import re
import urllib.request
import http.cookiejar
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "email_config.json"
DOWNLOAD_DIR = Path("C:/Users/Guille/Downloads/Videos_Primo")

def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "email": "tu_correo@gmail.com",
                "app_password": "tu_contraseña_de_aplicacion",
                "cousin_email": "correo_primo@gmail.com"
            }, f, indent=4)
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def connect_imap():
    config = load_config()
    if not config or "tu_correo" in config.get("email", ""):
        return None, "Por favor, configura el archivo email_config.json con tus datos."
    
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
        mail.login(config["email"], config["app_password"])
        return mail, None
    except Exception as e:
        return None, str(e)

def clean_and_decode_filename(fn_raw):
    if not fn_raw:
        return ""
    cleaned = fn_raw.replace("\r", "").replace("\n", "").strip()
    try:
        parts = decode_header(cleaned)
        decoded = []
        for content, enc in parts:
            if isinstance(content, bytes):
                decoded.append(content.decode(enc or 'utf-8', errors='ignore'))
            else:
                decoded.append(str(content))
        return " ".join("".join(decoded).split())
    except Exception:
        return cleaned

def get_emails_with_videos():
    config = load_config()
    mail, err = connect_imap()
    if not mail:
        return [], err
    
    try:
        mail.select("inbox")
        status, messages = mail.search(None, f'FROM "{config["cousin_email"]}"')
        
        email_list = []
        if status == "OK" and messages[0]:
            nums = messages[0].split()[-6:]  # Ultimos correos relevantes
            if nums:
                id_set = b",".join(nums)
                # Descarga ULTRA LIGERA por lote: estructura MIME, headers y texto de cuerpo (BODY.PEEK[1])
                # para detectar adjuntos directos Y archivos compartidos vía Google Drive (chips de Gmail).
                st, data = mail.fetch(id_set, '(BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)] BODY.PEEK[1])')
                
                valid_exts = {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'webm', 'jpg', 'jpeg', 'png', 'wfp', 'zip', 'rar', 'pdf', 'mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'}
                
                if st == "OK" and data:
                    msgs_data = {}
                    curr_id = None
                    for item in data:
                        if isinstance(item, tuple) and len(item) == 2:
                            tag = item[0].decode('latin1', errors='ignore')
                            raw = item[1].decode('latin1', errors='ignore') if isinstance(item[1], bytes) else str(item[1])
                            id_m = re.match(r'^\s*(\d+)', tag)
                            if id_m:
                                curr_id = id_m.group(1)
                            if curr_id:
                                if curr_id not in msgs_data:
                                    msgs_data[curr_id] = {"meta": "", "hdr": "", "body1": ""}
                                if "BODYSTRUCTURE" in tag:
                                    msgs_data[curr_id]["meta"] += tag
                                if "HEADER.FIELDS" in tag:
                                    msgs_data[curr_id]["hdr"] += raw
                                if "BODY[1]" in tag:
                                    msgs_data[curr_id]["body1"] += raw

                    for em_id, d in msgs_data.items():
                        subject = "(Sin Asunto)"
                        date_str = ""
                        for line in d["hdr"].splitlines():
                            if line.lower().startswith("subject:"):
                                raw_subj = line[8:].strip()
                                try:
                                    d_parts = decode_header(raw_subj)
                                    subj_decoded = "".join(p.decode(enc or 'utf-8', errors='ignore') if isinstance(p, bytes) else str(p) for p, enc in d_parts)
                                    subject = subj_decoded.strip() or "(Sin Asunto)"
                                except Exception:
                                    subject = raw_subj.strip() or "(Sin Asunto)"
                            elif line.lower().startswith("date:"):
                                date_str = line[5:].strip()

                        attachments = []
                        seen = set()

                        # 1. Adjuntos directos (MIME BODYSTRUCTURE)
                        raw_matches = re.findall(r'\"(?:filename|name)\"\s+\"([^\"]+)\"', d["meta"], re.IGNORECASE)
                        for raw_fn in raw_matches:
                            fn = clean_and_decode_filename(raw_fn)
                            if not fn:
                                continue
                            ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
                            if ext in valid_exts and fn.lower() not in seen:
                                seen.add(fn.lower())
                                attachments.append({
                                    "filename": fn,
                                    "is_drive": False,
                                    "drive_url": None
                                })

                        # 2. Archivos compartidos vía Google Drive en el cuerpo (chips de Gmail)
                        body1 = d["body1"]
                        drive_matches = []
                        for url, lbl in re.findall(r'<a\s+[^>]*href=[\"\'](https://drive\.google\.com/[^\"\']+)[\"\'][^>]*aria-label=[\"\']([^\"\']+)[\"\']', body1, re.IGNORECASE):
                            drive_matches.append((clean_and_decode_filename(lbl), url))
                        for lbl, url in re.findall(r'([^\r\n<>]+\.[a-zA-Z0-9]{2,5})\s*<(https://drive\.google\.com/[^>]+)>', body1):
                            drive_matches.append((clean_and_decode_filename(lbl), url))

                        for fn, url in drive_matches:
                            ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
                            if ext in valid_exts and fn.lower() not in seen:
                                seen.add(fn.lower())
                                attachments.append({
                                    "filename": fn,
                                    "is_drive": True,
                                    "drive_url": url
                                })

                        if attachments:
                            email_list.append({
                                "id": em_id,
                                "subject": subject,
                                "date": date_str,
                                "attachments": attachments
                            })

            # Ordenar de más reciente a más antiguo
            email_list.reverse()

        mail.logout()
        return email_list, None
    except Exception as e:
        try:
            mail.logout()
        except Exception:
            pass
        err_msg = str(e)
        if "OVERQUOTA" in err_msg.upper():
            return [], "Google Gmail ha aplicado un límite temporal de ancho de banda ([OVERQUOTA]) por descargas previas. Se restablecerá automáticamente en unos minutos."
        return [], err_msg

def download_from_google_drive(drive_url, destination_path):
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
    if not m:
        m = re.search(r'id=([a-zA-Z0-9_-]+)', drive_url)
    if not m:
        return False, "URL de Google Drive inválida"
    
    file_id = m.group(1)
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        req_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        req = urllib.request.Request(req_url, headers=headers)
        with opener.open(req, timeout=20) as resp:
            content_type = resp.headers.get('Content-Type', '')
            final_url = resp.geturl()
            
            # Descarga binaria directa (cuando no es página HTML)
            if 'text/html' not in content_type:
                with open(destination_path, 'wb') as out_f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out_f.write(chunk)
                return True, str(destination_path)
            
            # Si Google envió advertencia de tamaño (virus scan confirm), extraer token
            html = resp.read().decode('utf-8', errors='ignore')
            conf_m = re.search(r'confirm=([a-zA-Z0-9_-]+)', html)
            if conf_m:
                confirm_token = conf_m.group(1)
                conf_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm_token}"
                req2 = urllib.request.Request(conf_url, headers=headers)
                with opener.open(req2, timeout=40) as resp2:
                    ct2 = resp2.headers.get('Content-Type', '')
                    if 'text/html' not in ct2:
                        with open(destination_path, 'wb') as out_f:
                            while True:
                                chunk = resp2.read(65536)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                        return True, str(destination_path)

            if "accounts.google.com" in final_url or "accounts.google.com" in html:
                return False, "Google Drive bloqueó la descarga automática por permisos privados. Dile al primo que adjunte los archivos con el clip 📎 en Gmail para que se descarguen directo."
            return False, "No se pudo descargar automáticamente el archivo de Google Drive."
    except Exception as e:
        return False, f"Error al descargar de Drive: {e}"

def download_video(email_id, filename_to_download, drive_url=None):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Manejar si filename_to_download vino como dict
    if isinstance(filename_to_download, dict):
        if not drive_url:
            drive_url = filename_to_download.get("drive_url")
        filename_to_download = filename_to_download.get("filename", "")

    target_clean = clean_and_decode_filename(filename_to_download)
    target_norm = target_clean.replace(" ", "").lower()
    safe_name = "".join(c for c in target_clean if c not in '<>:"/\\|?*').strip()
    if not safe_name:
        safe_name = "archivo_descargado"
    filepath = DOWNLOAD_DIR / safe_name

    # Si tenemos el enlace de Drive, intentar descargarlo directamente sin navegador
    if drive_url:
        return download_from_google_drive(drive_url, filepath)

    mail, err = connect_imap()
    if not mail:
        return False, err
    
    try:
        mail.select("inbox")
        status, data = mail.fetch(email_id.encode() if isinstance(email_id, str) else email_id, '(RFC822)')
        if status != "OK":
            return False, "Email no encontrado"

        full_raw_body = ""
        for response_part in data:
            if isinstance(response_part, tuple):
                full_raw_body += response_part[1].decode('latin1', errors='ignore') if isinstance(response_part[1], bytes) else str(response_part[1])
                msg = email.message_from_bytes(response_part[1])
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                        
                        raw_filename = part.get_filename()
                        if raw_filename:
                            fname = clean_and_decode_filename(raw_filename)
                            fname_norm = fname.replace(" ", "").lower()

                            if (fname == filename_to_download or 
                                raw_filename == filename_to_download or 
                                fname == target_clean or 
                                fname_norm == target_norm or
                                target_norm in fname_norm or
                                fname_norm in target_norm):
                                
                                with open(filepath, 'wb') as f:
                                    f.write(part.get_payload(decode=True))
                                mail.logout()
                                return True, str(filepath)
        mail.logout()

        # Si no estuvo como adjunto MIME directo pero vino como link de Drive en el cuerpo
        drive_links = re.findall(r'https://drive\.google\.com/[^\s"\'<>]+', full_raw_body)
        if drive_links:
            return download_from_google_drive(drive_links[0], filepath)

        return False, "Archivo no encontrado en el correo"
    except Exception as e:
        try:
            mail.logout()
        except Exception:
            pass
        return False, str(e)
