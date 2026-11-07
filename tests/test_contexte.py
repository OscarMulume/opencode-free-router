"""Tests de la reduction de contexte Q3, sans appel reseau."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "litellm"))
import router_contexte as c  # noqa: E402


def gros_contexte(n=20, taille=4000):
    msgs = [{"role": "system", "content": "Tu es un agent de code."}]
    for i in range(n):
        role = "assistant" if i % 2 else "user"
        msgs.append({"role": role, "content": f"message {i} " + ("x" * taille)})
    msgs.append({"role": "user", "content": "QUESTION FINALE"})
    return msgs


class ContexteTest(unittest.TestCase):
    def test_petit_contexte_intact(self):
        msgs = [{"role": "user", "content": "bonjour"}]
        out, apres, actions = c.reduire(msgs, 8000)
        self.assertEqual(out, msgs)
        self.assertEqual(actions, [])

    def test_gros_contexte_reduit_et_derniere_question_preservee(self):
        msgs = gros_contexte()
        out, apres, actions = c.reduire(msgs, 8000)
        self.assertLessEqual(apres, 8000)
        self.assertGreater(len(actions), 0)
        self.assertEqual(out[-1]["content"], "QUESTION FINALE")
        self.assertEqual(out[0]["role"], "system")

    def test_pas_de_tool_orphelin(self):
        msgs = [{"role": "system", "content": "sys"}]
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]})
        msgs.append({"role": "tool", "content": "sortie" * 1000})
        for i in range(12):
            msgs.append({"role": "user", "content": f"u{i} " + "y" * 4000})
            msgs.append({"role": "assistant", "content": f"a{i} " + "z" * 4000})
        out, _, _ = c.reduire(msgs, 6000)
        for i, m in enumerate(out):
            if m["role"] == "tool":
                self.assertGreater(i, 0)
                self.assertEqual(out[i - 1].get("role"), "assistant")
                self.assertTrue(out[i - 1].get("tool_calls"))

    def test_limite_pour(self):
        limites = {"groupes": {"free-fast": 8000}, "modeles": {"ollama_chat/qwen2.5-coder:3b": 32768}}
        self.assertEqual(c.limite_pour("free-fast", limites), 8000)
        self.assertEqual(c.limite_pour("opencode-free-router/free-fast", limites), 8000)
        self.assertEqual(c.limite_pour("ollama_chat/qwen2.5-coder:3b", limites), 32768)
        self.assertEqual(c.limite_pour("inconnu", limites), c.DEFAUT)

    def test_charger_limites_et_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "limites.json"
            p.write_text(json.dumps({"groupes": {"free-fast": 8000}}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"FREE_ROUTER_LIMITS": str(p)}):
                self.assertEqual(c.limite_pour("free-fast", c.charger_limites()), 8000)
                data = {"model": "free-fast", "messages": gros_contexte()}
                c.LOG = Path(tmp) / "contexte.log"
                out = asyncio.run(c.proxy_handler_instance.async_pre_call_hook(None, None, data, "completion"))
                self.assertLessEqual(c.estimer(out["messages"]), 8000)
                self.assertTrue((Path(tmp) / "contexte.log").exists())
                ligne = json.loads((Path(tmp) / "contexte.log").read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(ligne["groupe"], "free-fast")
                self.assertNotIn("xxxx", json.dumps(ligne))


if __name__ == "__main__":
    unittest.main()
