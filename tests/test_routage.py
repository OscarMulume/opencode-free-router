"""Q4 : groupes par type de tache, modele de verification different, serveur d'epuisement."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
import epuise  # noqa: E402

BENCH = {"fournisseurs": {
    "gemini-3.5-flash-lite": {"modele": "gemini-3.5-flash-lite", "etat": "OK",
                               "1k": {"premier_token_s": 1.0}, "30k": {"premier_token_s": 2.0}},
    "gemini-3.6-flash": {"modele": "gemini-3.6-flash", "etat": "OK",
                          "1k": {"premier_token_s": 2.0}, "30k": {"premier_token_s": 3.0}},
}}
QUALITE = {"fournisseurs": {
    "gemini-3.5-flash-lite::gemini-3.5-flash-lite": {"score": 12, "total": 15, "note": 0.80, "retenu_free_auto": True},
    "gemini-3.6-flash::gemini-3.6-flash": {"score": 14, "total": 15, "note": 0.93, "retenu_free_auto": True},
}}


class RoutageTest(unittest.TestCase):
    def rendre(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "opencode-free-router"
            d.mkdir()
            (d / "bench.json").write_text(json.dumps(BENCH), encoding="utf-8")
            (d / "qualite.json").write_text(json.dumps(QUALITE), encoding="utf-8")
            env = dict(os.environ, LOCALAPPDATA=tmp, GEMINI_API_KEY="x", PYTHONUTF8="1")
            for k in ("GROQ_API_KEY", "GITHUB_MODELS_TOKEN"):
                env.pop(k, None)
            r = subprocess.run([sys.executable, str(RACINE / "scripts" / "render-config.py")], env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return yaml.safe_load((d / "litellm-config.yaml").read_text(encoding="utf-8"))

    @staticmethod
    def modeles(cfg, groupe):
        lst = [m for m in cfg["model_list"] if m["model_name"] == groupe]
        return [m["litellm_params"]["model"] for m in sorted(lst, key=lambda m: m["litellm_params"].get("order", 0))]

    def test_code_meilleur_score_en_premier(self):
        cfg = self.rendre()
        self.assertEqual(self.modeles(cfg, "free-code")[0], "gemini/gemini-3.6-flash")
        self.assertEqual(self.modeles(cfg, "free-auto")[0], "gemini/gemini-3.5-flash-lite")  # le plus rapide

    def test_verif_exclut_le_meilleur_de_code(self):
        cfg = self.rendre()
        self.assertNotIn("gemini/gemini-3.6-flash", self.modeles(cfg, "free-check"))
        self.assertEqual(self.modeles(cfg, "free-check"), ["gemini/gemini-3.5-flash-lite"])

    def test_question_ollama_en_dernier(self):
        cfg = self.rendre()
        q = self.modeles(cfg, "free-question")
        self.assertTrue(q[-1].startswith("ollama_chat/"))

    def test_epuise_serveur_puis_mock_et_fallbacks(self):
        cfg = self.rendre()
        ep = [m["litellm_params"] for m in cfg["model_list"] if m["model_name"] == "free-exhausted"]
        self.assertEqual(sorted(p["order"] for p in ep), [1, 2])
        self.assertTrue(any("mock_response" in p for p in ep))
        groupes = {list(f)[0] for f in cfg["router_settings"]["fallbacks"]}
        self.assertEqual(groupes, {"free-auto", "free-code", "free-check", "free-fast", "free-question"})
        self.assertNotIn("sk-", json.dumps(cfg))


class EpuiseTest(unittest.TestCase):
    def test_message_contient_heure_de_reprise(self):
        t0 = time.mktime((2026, 11, 7, 14, 0, 0, 0, 0, -1))
        self.assertIn("14:05", epuise.message_epuise(t0))

    def test_serveur_repond_tout_de_suite(self):
        serveur = ThreadingHTTPServer(("127.0.0.1", 0), epuise.Gestionnaire)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        port = serveur.server_address[1]
        try:
            for flux in (False, True):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/v1/chat/completions", method="POST",
                    data=json.dumps({"model": "free-exhausted", "stream": flux, "messages": []}).encode(),
                    headers={"Content-Type": "application/json"})
                debut = time.time()
                corps = urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
                self.assertLess(time.time() - debut, 2)
                self.assertIn("Reprise prevue vers", corps)
                self.assertEqual("[DONE]" in corps, flux)
        finally:
            serveur.shutdown()


if __name__ == "__main__":
    unittest.main()
