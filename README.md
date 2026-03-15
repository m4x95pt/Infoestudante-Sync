# Infoestudante-Sync

Script que sincroniza automaticamente dados académicos do portal Inforestudante (Universidade de Coimbra) para o Notion. Corre via GitHub Actions de hora em hora.

## O que faz

- Faz login no portal Inforestudante da UC
- Extrai dados académicos (notas, unidades curriculares, etc.)
- Sincroniza para uma base de dados Notion
- Corre automaticamente de hora em hora

## Stack

- **Linguagem:** Python 3
- **CI/CD:** GitHub Actions (cron job)
- **Integrações:** Inforestudante UC, Notion API

## Schedule

```
Corre de hora em hora, todos os dias
```

## Variáveis de ambiente / Secrets

```env
INFOESTUDANTE_USERNAME=...   # Número de estudante UC
INFOESTUDANTE_PASSWORD=...   # Password do portal
NOTION_TOKEN=...
NOTION_DATABASE_ID=...
```

No GitHub: **Settings → Secrets and variables → Actions**

## Instalação local

```bash
git clone https://github.com/m4x95pt/Infoestudante-Sync
cd Infoestudante-Sync
pip install -r requirements.txt
cp .env.example .env
# Preenche as variáveis
python main.py
```

## GitHub Actions

O workflow corre automaticamente:

```yaml
schedule:
  - cron: "0 * * * *"  # De hora em hora
```

Pode também ser acionado manualmente via **Actions → Run workflow**.

## Notas

- Mantém as credenciais do Inforestudante **apenas nos secrets do GitHub**, nunca em ficheiros versionados
- Se o portal da UC alterar a estrutura HTML, o script pode necessitar de atualização
