import os
import sys
import requests
from datetime import datetime, timedelta, date

# ─── Config ──────────────────────────────────────────────────────────────────
NOTION_TOKEN  = os.environ["NOTION_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK_URL"]

TOPICS_DB_ID  = "2a5c4bee31638103a42ee9e2fa528806"   # Assignments
TASKS_DB_ID   = "2a7c4bee3163813cbf9acda129ead602"   # Tasks
STRAVA_DB_ID  = "a7aecc46c1454d9494d7cfb2d87ba57e"   # Strava
EXPENSES_DB_ID= "30dc4bee316381e1b741d99f75355963"   # Expenses

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def notion_query(db_id, filters=None, sorts=None):
    body = {"page_size": 50}
    if filters:
        body["filter"] = filters
    if sorts:
        body["sorts"] = sorts
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=NOTION_HEADERS,
        json=body,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def prop_text(page, name):
    p = page.get("properties", {}).get(name, {})
    t = p.get("title") or p.get("rich_text") or []
    return t[0]["plain_text"] if t else ""


def prop_select(page, name):
    p = page.get("properties", {}).get(name, {})
    s = p.get("select") or p.get("status") or {}
    return s.get("name", "") if s else ""


def prop_date(page, name):
    p = page.get("properties", {}).get(name, {})
    d = p.get("date") or {}
    return d.get("start", "") if d else ""


def prop_number(page, name):
    p = page.get("properties", {}).get(name, {})
    return p.get("number")


def slack(text):
    requests.post(SLACK_WEBHOOK, json={"text": text})
    print(text)


def dias_restantes(data_str):
    if not data_str:
        return None
    try:
        d = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
        return (d - date.today()).days
    except ValueError:
        return None


def emoji_urgencia(dias):
    if dias is None:
        return ""
    if dias < 0:
        return "🔴"
    if dias <= 2:
        return "🔴"
    if dias <= 5:
        return "🟡"
    return "🟢"


# ─── Modo 1: Daily Digest ─────────────────────────────────────────────────────

def daily_digest():
    hoje = date.today()
    proximos_7 = (hoje + timedelta(days=7)).isoformat()
    hoje_str = hoje.isoformat()

    linhas = [f"☀️ *Bom dia! Digest de {hoje.strftime('%d/%m/%Y')}*", ""]

    # ── Assignments com deadline nos próximos 7 dias ─────────────────────────
    assignments = notion_query(TOPICS_DB_ID, filters={
        "and": [
            {"property": "date", "date": {"on_or_after": hoje_str}},
            {"property": "date", "date": {"on_or_before": proximos_7}},
            {"property": "type", "select": {"equals": "assignment"}},
            {"property": "Status", "status": {"does_not_equal": "done"}},
        ]
    }, sorts=[{"property": "date", "direction": "ascending"}])

    if assignments:
        linhas.append("*📚 Assignments com deadline esta semana:*")
        for a in assignments:
            nome = prop_text(a, "lecture/assignment")
            data = prop_date(a, "date")
            dias = dias_restantes(data)
            em = emoji_urgencia(dias)
            data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m") if data else "?"
            dias_txt = f" _(em {dias}d)_" if dias is not None else ""
            linhas.append(f"  {em} {nome} — *{data_fmt}*{dias_txt}")
    else:
        linhas.append("*📚 Assignments:* nenhum para esta semana 🎉")

    linhas.append("")

    # ── Tarefas pendentes ────────────────────────────────────────────────────
    tarefas = notion_query(TASKS_DB_ID, filters={
        "and": [
            {"property": "Status", "status": {"does_not_equal": "Done"}},
            {"property": "Status", "status": {"does_not_equal": "Inbox"}},
        ]
    })

    if tarefas:
        linhas.append("*✅ Tarefas pendentes:*")
        for t in tarefas:
            nome = prop_text(t, "Name")
            prioridade = prop_select(t, "Priority")
            p_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(prioridade, "•")
            due = prop_date(t, "Due Date")
            if due and len(due) > 10:
                dt = datetime.fromisoformat(due)
                due_fmt = f" · _{dt.strftime('%d/%m %H:%M')}_"
            elif due:
                due_fmt = f" · _{datetime.strptime(due[:10], '%Y-%m-%d').strftime('%d/%m')}_"
            else:
                due_fmt = ""
            linhas.append(f"  {p_emoji} {nome}{due_fmt}")
    else:
        linhas.append("*✅ Tarefas:* dia livre! 🎉")

    linhas.append("")

    # ── Último treino ────────────────────────────────────────────────────────
    treinos = notion_query(STRAVA_DB_ID, sorts=[{"property": "Data", "direction": "descending"}])
    if treinos:
        t = treinos[0]
        titulo = prop_text(t, "Name")
        tipo = prop_select(t, "Tipo")
        dist = prop_number(t, "Distância (km)")
        data = prop_date(t, "Data")
        data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m") if data else "?"
        dist_txt = f" · {dist:.1f}km" if dist else ""
        linhas.append(f"*🏃 Último treino:* {tipo} — {titulo}{dist_txt} _{data_fmt}_")
    else:
        linhas.append("*🏃 Strava:* sem treinos registados")

    linhas.append("")

    # ── Última despesa ────────────────────────────────────────────────────────
    despesas = notion_query(EXPENSES_DB_ID, sorts=[{"property": "Date", "direction": "descending"}])
    if despesas:
        d = despesas[0]
        source = prop_text(d, "Source")
        amount = prop_number(d, "Amount")
        tag = prop_select(d, "Tags")
        data = prop_date(d, "Date")
        data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m") if data else "?"
        amount_fmt = f" · *{amount:.2f}€*" if amount is not None else ""
        tag_fmt = f" · _{tag}_" if tag and tag != "—" else ""
        linhas.append(f"*💸 Última despesa:* {source}{amount_fmt}{tag_fmt} _{data_fmt}_")
    else:
        linhas.append("*💸 Despesas:* nenhuma registada")

    slack("\n".join(linhas))


# ─── Modo 2: Alertas de Deadline ─────────────────────────────────────────────

def deadline_alerts():
    hoje = date.today()
    alvo = (hoje + timedelta(days=3)).isoformat()

    assignments = notion_query(TOPICS_DB_ID, filters={
        "and": [
            {"property": "date", "date": {"equals": alvo}},
            {"property": "type", "select": {"equals": "assignment"}},
            {"property": "Status", "status": {"does_not_equal": "done"}},
        ]
    })

    if not assignments:
        print("Sem alertas de deadline para hoje.")
        return

    linhas = ["⚠️ *Deadline em 3 dias!*", ""]
    for a in assignments:
        nome = prop_text(a, "lecture/assignment")
        data = prop_date(a, "date")
        data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m/%Y") if data else "?"
        url = a.get("url", "")
        linhas.append(f"  📋 *{nome}*")
        linhas.append(f"      Entrega: *{data_fmt}*")
        if url:
            linhas.append(f"      <{url}|Ver no Notion>")

    slack("\n".join(linhas))


# ─── Modo 3: Resumo Semanal ───────────────────────────────────────────────────

def weekly_summary():
    hoje = date.today()
    segunda = hoje - timedelta(days=hoje.weekday())
    domingo = segunda + timedelta(days=6)
    segunda_str = segunda.isoformat()
    domingo_str = domingo.isoformat()

    linhas = [
        f"📊 *Resumo da semana — {segunda.strftime('%d/%m')} a {domingo.strftime('%d/%m/%Y')}*",
        ""
    ]

    # ── Treinos da semana ────────────────────────────────────────────────────
    treinos = notion_query(STRAVA_DB_ID, filters={
        "and": [
            {"property": "Data", "date": {"on_or_after": segunda_str}},
            {"property": "Data", "date": {"on_or_before": domingo_str}},
        ]
    })

    if treinos:
        total_km = sum(prop_number(t, "Distância (km)") or 0 for t in treinos)
        linhas.append(f"*🏃 Treinos:* {len(treinos)} treino(s) · {total_km:.1f}km no total")
        for t in treinos:
            tipo = prop_select(t, "Tipo")
            dist = prop_number(t, "Distância (km)")
            data = prop_date(t, "Data")
            data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m") if data else "?"
            dist_txt = f" · {dist:.1f}km" if dist else ""
            linhas.append(f"  • {tipo}{dist_txt} _{data_fmt}_")
    else:
        linhas.append("*🏃 Treinos:* nenhum esta semana")

    linhas.append("")

    # ── Assignments entregues/pendentes ──────────────────────────────────────
    feitos = notion_query(TOPICS_DB_ID, filters={
        "and": [
            {"property": "type", "select": {"equals": "assignment"}},
            {"property": "Status", "status": {"equals": "done"}},
            {"property": "date", "date": {"on_or_after": segunda_str}},
            {"property": "date", "date": {"on_or_before": domingo_str}},
        ]
    })

    pendentes = notion_query(TOPICS_DB_ID, filters={
        "and": [
            {"property": "type", "select": {"equals": "assignment"}},
            {"property": "Status", "status": {"does_not_equal": "done"}},
            {"property": "date", "date": {"on_or_before": domingo_str}},
        ]
    })

    linhas.append(f"*📚 Assignments:* {len(feitos)} concluído(s)")
    if feitos:
        for a in feitos:
            linhas.append(f"  ✅ {prop_text(a, 'lecture/assignment')}")

    if pendentes:
        linhas.append(f"*⏳ Pendentes ({len(pendentes)}):*")
        for a in pendentes[:5]:
            nome = prop_text(a, "lecture/assignment")
            data = prop_date(a, "date")
            dias = dias_restantes(data)
            em = emoji_urgencia(dias)
            data_fmt = datetime.strptime(data[:10], "%Y-%m-%d").strftime("%d/%m") if data else "?"
            linhas.append(f"  {em} {nome} — {data_fmt}")

    linhas.append("")

    # ── Despesas da semana ───────────────────────────────────────────────────
    despesas = notion_query(EXPENSES_DB_ID, filters={
        "and": [
            {"property": "Date", "date": {"on_or_after": segunda_str}},
            {"property": "Date", "date": {"on_or_before": domingo_str}},
        ]
    })

    if despesas:
        total = sum(prop_number(d, "Amount") or 0 for d in despesas)
        linhas.append(f"*💸 Despesas:* {len(despesas)} transacção(ões) · *{total:.2f}€* no total")
    else:
        linhas.append("*💸 Despesas:* nenhuma registada esta semana")

    slack("\n".join(linhas))


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"

    if mode == "daily":
        daily_digest()
    elif mode == "deadline":
        deadline_alerts()
    elif mode == "weekly":
        weekly_summary()
    else:
        print(f"Modo desconhecido: {mode}. Usa: daily | deadline | weekly")
        sys.exit(1)
