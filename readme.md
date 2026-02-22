# SmartClipboard

A local, privacy-first clipboard workspace for rewriting, summarising, reformatting and extracting structured information using local LLMs via Ollama.

SmartClipboard keeps your data on your machine. No cloud APIs required.

---

## Why SmartClipboard?

SmartClipboard is designed for people who:

- Want AI-powered text tools
- Care about privacy
- Prefer local-first software
- Use Ollama for running LLMs locally

Your clipboard history, AI prompts, and generated outputs stay on your device.

---

## Features

- Clipboard history stored locally (SQLite)
- Composer workspace for combining clips
- AI actions (rewrite, summarise, reformat, extract, etc.)
- Personas (JSON-driven)
- Model detection from Ollama
- Optional capture safety controls (blocklist + secret heuristics)

---

## Requirements

- Python 3.10+ recommended
- Ollama installed and running locally

You can download Ollama from: https://ollama.com

---

## Install

```bash
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## How It Works (High-Level)

1. SmartClipboard monitors and stores clipboard entries locally.
2. You can combine clips inside the Composer workspace.
3. AI actions are executed using your locally running Ollama models.
4. Results are stored locally and never sent to external services.

---

## Privacy

SmartClipboard is designed to run entirely on your machine.

- No remote AI APIs
- No telemetry
- No background cloud calls

All AI processing happens through your local Ollama instance.

---

## Contributing

Contributions, improvements, and ideas are welcome.

If you'd like to contribute:

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Open a Pull Request

---

## License

This project is licensed under the MIT License — see the LICENSE file for details.