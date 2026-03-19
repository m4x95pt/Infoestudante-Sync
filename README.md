# Infoestudante-Sync

## Overview

This Python tool reads Gmail notifications from the University of Coimbra’s Infoestudante platform about new assignments, extracts assignment data, and adds them automatically to your Notion database.

## Features

- **Automated Gmail parsing:** Scans your Gmail inbox for Infoestudante notifications about new assignments.
- **Data extraction:** Parses email contents to get assignment information (name, date, course, etc).
- **Notion integration:** Adds or updates assignments in your personal Notion workspace.
- **Scheduled automation:** Can run via cron jobs or GitHub Actions.

## Requirements

- Python 3.x
- `requests` library
- Gmail App Password (for authentication)
- Notion integration token

## Usage

1. Clone the repository:

   ```bash
   git clone https://github.com/m4x95pt/Infoestudante-Sync
   cd Infoestudante-Sync
   pip install requests
   ```

2. Set up environment variables:

   ```env
   NOTION_TOKEN=...
   GMAIL_APP_PASSWORD=...
   # Other variables as needed
   ```

3. Run the script:

   ```bash
   python sync_infoestudante.py
   ```

4. (Optional) Schedule it using cron or GitHub Actions for regular syncing.

## Notion Database

- Make sure to configure the database ID in the script if your Notion workspace differs.

## License

MIT License

**Author:** [@m4x95pt](https://github.com/m4x95pt)
