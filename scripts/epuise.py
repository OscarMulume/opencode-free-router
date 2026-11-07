"""Mini-serveur OpenAI-compatible : repond tout de suite quand tous les quotas sont epuises (Q4).

LiteLLM ne sait pas renvoyer un message assistant depuis un hook (une str leve RejectedRequestError).
free-exhausted est donc un deploiement openai/ pointe ici : la reponse est un vrai message assistant,
avec l'heure de reprise calculee a chaque appel (maintenant + DELAI_MIN). Aucune cle, aucun contenu journalise.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOTE, PORT = "127.0.0.1", 4010
DELAI_MIN = 5


def message_epuise(maintenant=None):
    t = (maintenant if maintenant is not None else time.time()) + DELAI_MIN * 60
    heure = time.strftime("%H:%M", time.localtime(t))
    return (f"Quotas gratuits epuises : tous les fournisseurs (Gemini, Groq, Ollama) sont en pause. "
            f"Reprise prevue vers {heure} (dans environ {DELAI_MIN} minutes). "
            f"Poussez votre travail, puis reessayez a cette heure ou utilisez Claude Code.")


def corps_reponse(modele="free-exhausted"):
    return {"id": "chatcmpl-epuise", "object": "chat.completion", "created": int(time.time()), "model": modele,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": message_epuise()}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


def corps_flux(modele="free-exhausted"):
    base = {"id": "chatcmpl-epuise", "object": "chat.completion.chunk", "created": int(time.time()), "model": modele}
    morceaux = [dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": message_epuise()},
                                     "finish_reason": None}]),
                dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])]
    return "".join("data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in morceaux) + "data: [DONE]\n\n"


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _envoyer(self, code, contenu, type_="application/json"):
        data = contenu.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_ + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/health") or self.path.startswith("/v1/models"):
            self._envoyer(200, json.dumps({"status": "ok", "data": [{"id": "free-exhausted", "object": "model"}]}))
        else:
            self._envoyer(404, "{}")

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        try:
            requete = json.loads(self.rfile.read(longueur) or b"{}")
        except Exception:
            requete = {}
        modele = str(requete.get("model") or "free-exhausted")
        if requete.get("stream"):
            self._envoyer(200, corps_flux(modele), "text/event-stream")
        else:
            self._envoyer(200, json.dumps(corps_reponse(modele), ensure_ascii=False))


def main() -> int:
    serveur = ThreadingHTTPServer((HOTE, PORT), Gestionnaire)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
