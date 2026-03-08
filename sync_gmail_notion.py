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
TASKS_DB_ID        = "2a7c4bee3163813cbf9acda129ead602"
GMAIL_LABEL        = "inforestudante"  # label que criaste no Gmail

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ─── Gmail: ligar e buscar emails não lidos com a label ──────────────────────

def get_emails():
    print("📬 A ligar ao Gmail...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)

    # Seleccionar a label (no IMAP as labels do Gmail são "pastas")
    status, _ = mail.select(f'"{GMAIL_LABEL}"')
    if status != "OK":
        print(f"  ⚠️  Label '{GMAIL_LABEL}' não encontrada")
        mail.logout()
        return []

    # Buscar emails não lidos
    status, data = mail.search(None, "UNSEEN")
    if status != "OK" or not data[0]:
        print("  ✓ Sem emails novos")
        mail.logout()
        return []

    email_ids = data[0].split()
    print(f"  ✓ {len(email_ids)} email(s) novo(s) encontrado(s)")

    emails = []
    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        # Extrair corpo do email
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

        # Marcar como lido (para não processar novamente)
        mail.store(eid, "+FLAGS", "\\Seen")

    mail.logout()
    return emails


# ─── Parser: extrair dados do email ──────────────────────────────────────────

def parse_email(subject, body):
    """
    Extrai disciplina, nome do trabalho, data início e data limite do email.
    Os emails do noreply@ruvse.pt têm um formato consistente.
    """
    result = {
        "disciplina": None,
        "trabalho": None,
        "data_inicio": None,
        "data_limite": None,
    }

    # Normalizar texto
    text = body.replace("\r\n", "\n").replace("\r", "\n")

    # Tentar extrair disciplina
    for pattern in [
        r"disciplina[:\s]+([^\n]+)",
        r"unidade curricular[:\s]+([^\n]+)",
        r"UC[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["disciplina"] = m.group(1).strip()
            break

    # Tentar extrair nome do trabalho
    for pattern in [
        r"trabalho[:\s]+([^\n]+)",
        r"submiss[aã]o[:\s]+([^\n]+)",
        r"tarefa[:\s]+([^\n]+)",
        r"avalia[cç][aã]o[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["trabalho"] = m.group(1).strip()
            break

    # Se não encontrou o nome do trabalho, usar o assunto do email
    if not result["trabalho"] and subject:
        result["trabalho"] = subject.strip()

    # Tentar extrair datas (formato dd-mm-yyyy hh:mm ou dd/mm/yyyy)
    date_patterns = [
        r"(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]

    dates_found = []
    for pattern in date_patterns:
        dates_found = re.findall(pattern, text)
        if dates_found:
            break

    # Tentar extrair data limite especificamente
    for pattern in [
        r"(?:data\s+limite|prazo|limite de entrega|until|até)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
        r"(?:data\s+fim|fim)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_limite"] = parse_date(m.group(1))
            break

    # Tentar extrair data início
    for pattern in [
        r"(?:data\s+in[ií]cio|in[ií]cio|from|a partir de)[:\s]+(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2})?)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result["data_inicio"] = parse_date(m.group(1))
            break

    # Se só encontrou datas genéricas e não as identificou acima
    if dates_found and not result["data_limite"]:
        # Assumir que a última data encontrada é o limite
        result["data_limite"] = parse_date(dates_found[-1])
    if dates_found and not result["data_inicio"] and len(dates_found) > 1:
        result["data_inicio"] = parse_date(dates_found[0])

    return result


def parse_date(date_str):
    """Converte dd-mm-yyyy ou dd/mm/yyyy em yyyy-mm-dd."""
    date_str = date_str.strip()
    for fmt in ["%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ─── Notion: verificar se tarefa já existe ───────────────────────────────────

def task_exists(name):
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{TASKS_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={
            "filter": {
                "property": "Name",
                "title": {"equals": name}
            }
        }
    )
    resp.raise_for_status()
    return len(resp.json().get("results", [])) > 0


# ─── Notion: criar tarefa ────────────────────────────────────────────────────

def create_task(disciplina, trabalho, data_limite):
    nome = f"{disciplina}: {trabalho}" if disciplina else trabalho

    if task_exists(nome):
        print(f"  — Já existe: {nome}")
        return

    body = {
        "parent": {"database_id": TASKS_DB_ID},
        "properties": {
            "Name":     {"title": [{"text": {"content": nome}}]},
            "Status":   {"status": {"name": "To-Do"}},
            "Tag":      {"select": {"name": "Study"}},
            "Priority": {"select": {"name": "High"}},
        }
    }

    if data_limite:
        body["properties"]["Due Date"] = {"date": {"start": data_limite}}

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=body,
    )
    resp.raise_for_status()
    due_str = f" · Due: {data_limite}" if data_limite else ""
    print(f"  ✅ Criada: {nome}{due_str}")


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
            print(f"     Disciplina: {data['disciplina']}")
            print(f"     Trabalho:   {data['trabalho']}")
            print(f"     Início:     {data['data_inicio']}")
            print(f"     Limite:     {data['data_limite']}")

            if data["trabalho"]:
                create_task(data["disciplina"], data["trabalho"], data["data_limite"])
            else:
                print(f"  ⚠️  Não foi possível extrair dados do email")

        print("\n✅ Processamento concluído!")
