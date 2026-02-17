from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_models(self, timeout_s: float = 2.5) -> List[str]:
        """
        GET /api/tags -> {"models":[{"name":"..."}]}
        """
        url = f"{self.base_url}/api/tags"
        r = requests.get(url, timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
        models = data.get("models", []) or []
        names: List[str] = []
        for m in models:
            n = m.get("name")
            if isinstance(n, str) and n.strip():
                names.append(n.strip())
        # stable, predictable order
        return sorted(set(names), key=str.lower)

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        timeout_s: float = 60.0,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        POST /api/chat
        """
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if options:
            payload["options"] = options

        r = requests.post(url, json=payload, timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message", {}) or {}
        content = msg.get("content", "")
        return content if isinstance(content, str) else str(content)
