# Infoestudante-Sync

Automação que monitoriza emails do **NONIO** (plataforma de entrega de trabalhos da UC) via Gmail e cria automaticamente assignments no Notion, com notificação no Slack.

## Como funciona

1. Liga ao Gmail via IMAP e procura emails **não lidos** com a label `inforestudante`
2. Filtra apenas notificações de submissão de trabalhos (assunto contém `Notifica` + `Submiss`)
3. Extrai do email: disciplina (pelo código no assunto), nome do trabalho e data limite
4. Encontra a cadeira correspondente na DB `Domains` do Notion (por código ou nome)
5. Cria o assignment na DB `Topics` do Notion (se ainda não existir)
6. Envia notificação para Slack com os detalhes do novo trabalho
7. Marca o email como lido no Gmail

## Ficheiros

```
Infoestudante-Sync/
├── sync_gmail_notion.py          # Script principal — Gmail → Notion
├── slack_notify.py               # Daily digest, alertas de deadline e resumo semanal
└── .github/workflows/
    ├── sync-gmail-notion.yml     # Cron: de hora em hora
    └── slack-notify.yml          # Cron: digest diário, alertas, resumo semanal
```

## Stack

- **Linguagem:** Python 3.12
- **Email:** Gmail IMAP (`imaplib`) + App Password
- **Integrações:** Notion API, Slack Incoming Webhook
- **CI/CD:** GitHub Actions

## Schedules

| Workflow | Schedule | Descrição |
|----------|----------|-----------|
| `sync-gmail-notion` | De hora em hora | Verifica novos emails do NONIO |
| `slack-notify daily` | 08:00 Lisboa | Digest diário (assignments, tarefas, treino, despesas) |
| `slack-notify deadline` | 08:30 Lisboa | Alerta de deadlines em 3 dias |
| `slack-notify weekly` | Domingo 20:00 Lisboa | Resumo semanal |

## Bases de dados Notion

| DB | Descrição | ID |
|----|-----------|-----|
| Topics | Assignments / trabalhos | `2a5c4bee31638103a42ee9e2fa528806` |
| Domains | Cadeiras / unidades curriculares | `2a5c4bee316381cbadc0c231753c492d` |
| Tasks | Tarefas pessoais | `2a7c4bee3163813cbf9acda129ead602` |
| Strava | Treinos | `a7aecc46c1454d9494d7cfb2d87ba57e` |
| Expenses | Despesas | `30dc4bee316381e1b741d99f75355963` |

## Secrets necessários

```env
GMAIL_USER=...             # Endereço Gmail
GMAIL_APP_PASSWORD=...     # App Password (não a password normal)
NOTION_TOKEN=...           # Integration Secret (começa com secret_)
SLACK_WEBHOOK_URL=...      # Incoming Webhook do canal Slack
```

> ⚠️ Usa uma **App Password** do Google, não a tua password normal.  
> Gera em: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requer 2FA ativo)

No GitHub: **Settings → Secrets and variables → Actions → New repository secret**

## Instalação local

```bash
git clone https://github.com/m4x95pt/Infoestudante-Sync
cd Infoestudante-Sync
pip install requests
python sync_gmail_notion.py
```

## Configuração do Gmail

É necessário criar uma label `inforestudante` no Gmail e configurar um filtro para que os emails do NONIO sejam automaticamente arquivados com essa label:

1. Gmail → Definições → **Filtros e endereços bloqueados** → Criar novo filtro
2. Campo **De:** preenche com o remetente dos emails do NONIO
3. Ação: **Aplicar a label** `inforestudante`

## Formato dos emails suportados

O parser reconhece emails do NONIO com o seguinte formato:

**Assunto:** `[NONIO] PMA - Notificação de Submissão de Trabalhos`  
**Corpo:**
```
submissão de trabalhos Meta 4 – As Cidades Invisíveis – Pré-produção.
A data limite para entrega é 04-04-2026 22:00
Pode submeter a entrega a partir de 05-03-2026 14:00
```

### Abreviações de cadeiras suportadas

| Código | Cadeira |
|--------|---------|
| `PMA` | Projeto 2 - Audiovisual |
| `PA` | Produção Audiovisual |
| `CG` | Computação Gráfica |
| `FC` | Fotografia e Composição |
| `TI` | Tecnologias da Internet |
| `P1` | Projeto 1 - Identidade |
| `TMD` | Tipografia em Meios Digitais |
| `ACM` | Arte e Cultura Moderna |

Para adicionar novas cadeiras, edita o dicionário `ABREVIACOES` em `sync_gmail_notion.py`.

## Notas

- O script só processa emails **não lidos** — após processar, marca-os como lidos
- Duplicados são evitados: se um assignment com o mesmo nome já existir no Notion, não é criado novamente
- O `slack_notify.py` também agrega dados de Strava e Expenses para o digest diário e resumo semanal
