import os
import imaplib
import email
import re
from datetime import datetime
import requests

# ─── Config ──────────────────────────────────────────────────────────────────
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]

# Study Scheduler — Topics (assignments) e Domains (cadeiras)
TOPICS_DS_ID  = "2a5c4bee-3163-8114-906a-000b84fdbcd0"
DOMAINS_DS_ID = "2a5c4bee-3163-8119-bff1-000bac57ab22"
GMAIL_LABEL   = "inforestudante"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ─── Gmail: buscar emails não lidos com a label ───────────────────────────────

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

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        emails.append({
            "id": eid,
            "subject": msg.get("Subject", ""),
            "body": body,
        })

        # Marcar como lido para não processar de novo
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

    # Disciplina
    for pattern in [
        r"(?:disciplina|unidade curricular|UC)[:\s]+([^\n]+)",
        r"(?:course|cadeira)[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["disciplina"] = m.group(1).strip()
            break

    # Nome do trabalho
    for pattern in [
        r"(?:trabalho|submiss[aã]o|tarefa|avalia[cç][aã]o|assignment)[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["trabalho"] = m.group(1).strip()
            break

    if not result["trabalho"]:
        result["trabalho"] = subject.strip()

    # Data limite
    for pattern in [
        r"(?:data\s+limite|prazo|limite de entrega|data\s+fim|fim)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_limite"] = parse_date(m.group(1))
            break

    # Data início
    for pattern in [
        r"(?:data\s+in[ií]cio|in[ií]cio|a partir de)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_inicio"] = parse_date(m.group(1))
            break

    # Se não encontrou datas pelos labels, tenta encontrar todas as datas no texto
    if not result["data_limite"]:
        dates = re.findall(r"\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?", text)
        if dates:
            result["data_limite"] = parse_date(dates[-1])
        if len(dates) > 1:
            result["data_inicio"] = parse_date(dates[0])

    return result


# ─── Notion: encontrar cadeira pelo nome ─────────────────────────────────────

def find_domain_by_name(disciplina_nome):
    """Procura a cadeira no Domains pelo nome ou código."""
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{DOMAINS_DS_ID}/query",
        headers=NOTION_HEADERS,
        json={"page_size": 50},
    )
    resp.raise_for_status()
    pages = resp.json().get("results", [])

    disciplina_lower = disciplina_nome.lower().strip()

    for page in pages:
        props = page.get("properties", {})

        # Verificar pelo nome
        name_prop = props.get("Name", {})
        name_items = name_prop.get("title", [])
        name = name_items[0]["plain_text"].lower() if name_items else ""

        # Verificar pelo course code
        code_prop = props.get("course code", {})
        code_items = code_prop.get("rich_text", [])
        code = code_items[0]["plain_text"].lower() if code_items else ""

        if disciplina_lower in name or name in disciplina_lower or disciplina_lower == code:
            print(f"  ✓ Cadeira encontrada: {name_items[0]['plain_text'] if name_items else '?'}")
            return page["url"], page["id"]

    print(f"  ⚠️  Cadeira não encontrada: {disciplina_nome}")
    return None, None


# ─── Notion: verificar se assignment já existe ────────────────────────────────

def assignment_exists(nome):
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{TOPICS_DS_ID}/query",
        headers=NOTION_HEADERS,
        json={
            "filter": {
                "property": "lecture/assignment",
                "title": {"equals": nome}
            }
        }
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
        "parent": {"database_id": TOPICS_DS_ID},
        "properties": {
            "lecture/assignment": {"title": [{"text": {"content": nome}}]},
            "type":               {"select": {"name": "assignment"}},
            "Status":             {"status": {"name": "not started"}},
        }
    }

    # Ligar à cadeira (relação domain)
    if domain_url:
        body["properties"]["domain"] = {
            "relation": [{"url": domain_url}]
        }

    # Data limite
    if data_limite:
        body["properties"]["date"] = {"date": {"start": data_limite}}

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=body,
    )
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
            print(f"\n  📧 Assunto: {e['subject']}")
            data = parse_email(e["subject"], e["body"])
            print(f"     Disciplina:  {data['disciplina']}")
            print(f"     Trabalho:    {data['trabalho']}")
            print(f"     Data limite: {data['data_limite']}")

            if not data["trabalho"]:
                print("  ⚠️  Não foi possível extrair o nome do trabalho")
                continue

            # Encontrar a cadeira no Notion
            domain_url, domain_id = None, None
            if data["disciplina"]:
                domain_url, domain_id = find_domain_by_name(data["disciplina"])

            create_assignment(data["disciplina"], data["trabalho"], data["data_limite"], domain_url)

        print("\n✅ Processamento concluído!")
