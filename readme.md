\# SmartClipboard



A local, privacy-first clipboard workspace for rewriting, summarising, reformatting and extracting structured information using local LLMs via Ollama.



\## Features

\- Clipboard history stored locally (SQLite)

\- Composer workspace for combining clips

\- AI actions (rewrite, summarise, reformat, extract, etc.)

\- Personas (JSON-driven)

\- Model detection from Ollama

\- Optional capture safety controls (blocklist + secret heuristics)



\## Requirements

\- Python 3.10+ recommended

\- Ollama installed and running locally



\## Install

```bash

python -m venv env

env\\Scripts\\activate

pip install -r requirements.txt

python app.py



