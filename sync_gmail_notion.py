import os
import imaplib
import email
import email.header
import re
import html
from datetime import datetime
import requests

# ─── Config ──────────────────────────────────────────────────────────────────
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]

# IDs correctos das databases (page IDs, não collection IDs)
TOPICS_DB_ID  = "2a5c4bee31638103a42ee9e2fa528806"   # Topics (assignments)
DOMAINS_DB_ID = "2a5c4bee316381cbadc0c231753c492d"   # Domains (cadeiras)
GMAIL_LABEL   = "inforestudante"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ─── Gmail: buscar emails não lidos com a label ───────────────────────────────

def decode_subject(subject_raw):
    """Decodifica assunto em RFC 2047 (=?UTF-8?Q?...?=)."""
    parts = email.header.decode_header(subject_raw)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def clean_body(body):
    """Remove HTML tags e normaliza espaços."""
    # Converter <br/> e <br> em newlines
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    # Remover todas as tags HTML
    body = re.sub(r"<[^>]+>", "", body)
    # Decode HTML entities (&amp; &lt; etc.)
    body = html.unescape(body)
    # Normalizar espaços
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def get_emails():
    print("📬 A ligar ao Gmail...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)

    status, _ = mail.select(f'"{GMAIL_LABEL}"')
    if status != "OK":
        print(f"  ⚠️  Label '{GMAIL_LABEL}' não encontrada no Gmail")
        mail.logout()
        return []

    status, data = mail.search(None, "UNSEEN")
    if status != "OK" or not data[0]:
        print("  ✓ Sem emails novos")
        mail.logout()
        return []

    email_ids = data[0].split()
    print(f"  ✓ {len(email_ids)} email(s) novo(s)")

    emails = []
    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])

        # Extrair e decodificar assunto
        subject_raw = msg.get("Subject", "")
        subject = decode_subject(subject_raw)

        # Extrair corpo — preferir text/plain, fallback para text/html
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
                elif ct == "text/html" and not body:
                    raw_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    body = clean_body(raw_html)
        else:
            raw = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            body = clean_body(raw)

        print(f"\n  📧 Assunto decodificado: {subject}")
        print(f"  Corpo:\n{body[:500]}\n---")

        emails.append({"id": eid, "subject": subject, "body": body})
        mail.store(eid, "+FLAGS", "\\Seen")

    mail.logout()
    return emails


# ─── Parser: extrair dados do email ──────────────────────────────────────────

def parse_date(date_str):
    date_str = date_str.strip()
    for fmt in ["%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_email(subject, body):
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    result = {"disciplina": None, "trabalho": None, "data_inicio": None, "data_limite": None}

    # Disciplina — padrões comuns nos emails do nonio
    for pattern in [
        r"(?:disciplina|unidade curricular|UC|cadeira)[:\s]+([^\n]+)",
        r"(?:course)[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["disciplina"] = m.group(1).strip()
            break

    # Nome do trabalho — linha antes das datas
    for pattern in [
        r"(?:trabalho|submiss[aã]o de trabalhos?|tarefa|avalia[cç][aã]o|entrega)[:\s«»\"\']*([^\n<]{3,80})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip(".")
            # Ignorar se começar com "de trabalhos" (é o título da notificação)
            if not re.match(r"^de trabalho", val, re.IGNORECASE):
                result["trabalho"] = val
                break

    # Fallback: usar assunto do email limpo
    if not result["trabalho"]:
        clean_subj = re.sub(r"\[NONIO\]|\[.*?\]", "", subject).strip()
        result["trabalho"] = clean_subj if clean_subj else subject

    # Data limite
    for pattern in [
        r"(?:data limite.*?é|prazo|limite de entrega|data\s+fim)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
        r"(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)[^\n]*(?:limite|prazo|fim|deadline)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_limite"] = parse_date(m.group(1))
            break

    # Data início
    for pattern in [
        r"(?:a partir de|data\s+in[ií]cio|in[ií]cio)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
        r"submeter.*?a partir de\s+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_inicio"] = parse_date(m.group(1))
            break

    # Fallback: apanhar todas as datas no texto
    if not result["data_limite"]:
        dates = re.findall(r"\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?", text)
        if dates:
            result["data_limite"] = parse_date(dates[-1])
        if len(dates) > 1 and not result["data_inicio"]:
            result["data_inicio"] = parse_date(dates[0])

    return result


# ─── Notion: encontrar cadeira pelo nome ─────────────────────────────────────

def find_domain_by_name(disciplina_nome):
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{DOMAINS_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"page_size": 50},
    )
    resp.raise_for_status()
    pages = resp.json().get("results", [])

    disciplina_lower = disciplina_nome.lower().strip()

    for page in pages:
        props = page.get("properties", {})
        name_items = props.get("Name", {}).get("title", [])
        name = name_items[0]["plain_text"].lower() if name_items else ""
        code_items = props.get("course code", {}).get("rich_text", [])
        code = code_items[0]["plain_text"].lower() if code_items else ""

        if disciplina_lower in name or name in disciplina_lower or disciplina_lower == code:
            print(f"  ✓ Cadeira encontrada: {name_items[0]['plain_text'] if name_items else '?'}")
            return page["url"], page["id"]

    print(f"  ⚠️  Cadeira não encontrada: '{disciplina_nome}'")
    return None, None


# ─── Notion: verificar se assignment já existe ────────────────────────────────

def assignment_exists(nome):
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{TOPICS_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"filter": {"property": "lecture/assignment", "title": {"equals": nome}}}
    )
    resp.raise_for_status()
    return len(resp.json().get("results", [])) > 0


# ─── Notion: criar assignment no Study Scheduler ─────────────────────────────

def create_assignment(disciplina_nome, trabalho_nome, data_limite, domain_url):
    nome = f"{disciplina_nome}: {trabalho_nome}" if disciplina_nome else trabalho_nome

    if assignment_exists(nome):
        print(f"  — Já existe: {nome}")
        return

    body = {
        "parent": {"database_id": TOPICS_DB_ID},
        "properties": {
            "lecture/assignment": {"title": [{"text": {"content": nome}}]},
            "type":               {"select": {"name": "assignment"}},
            "Status":             {"status": {"name": "not started"}},
        }
    }

    if domain_url:
        body["properties"]["domain"] = {"relation": [{"url": domain_url}]}

    if data_limite:
        body["properties"]["date"] = {"date": {"start": data_limite}}

    resp = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=body)
    resp.raise_for_status()
    due_str = f" · Due: {data_limite}" if data_limite else ""
    print(f"  ✅ Assignment criado: {nome}{due_str}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    emails = get_emails()

    if not emails:
        print("✅ Nada a processar.")
    else:
        print(f"\n📝 A processar {len(emails)} email(s)...")
        for e in emails:
            data = parse_email(e["subject"], e["body"])
            print(f"  Disciplina:  {data['disciplina']}")
            print(f"  Trabalho:    {data['trabalho']}")
            print(f"  Data início: {data['data_inicio']}")
            print(f"  Data limite: {data['data_limite']}")

            if not data["trabalho"]:
                print("  ⚠️  Não foi possível extrair o nome do trabalho")
                continue

            domain_url = None
            if data["disciplina"]:
                domain_url, _ = find_domain_by_name(data["disciplina"])

            create_assignment(data["disciplina"], data["trabalho"], data["data_limite"], domain_url)

        print("\n✅ Processamento concluído!")
