"""Rendering test: with NO provider key, render-config must produce a valid config, write no secret,
and keep the exhausted-quota fallback. Run: python -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_MODELS_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
        "NVIDIA_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY"]


def render(extra_env=None):
    tmp = tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items() if k not in KEYS}
    env.update({"LOCALAPPDATA": tmp, "HOME": tmp, "USERPROFILE": tmp, "FREE_ROUTER_NO_REGISTRY": "1"})
    env.update(extra_env or {})
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "render-config.py")], env=env, capture_output=True, text=True)
    return result, Path(tmp) / "opencode-free-router" / "litellm-config.yaml"


class RenderTest(unittest.TestCase):
    def test_without_keys(self):
        result, config = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = yaml.safe_load(config.read_text(encoding="utf-8"))
        names = {m["model_name"] for m in data["model_list"]}
        self.assertTrue({"free-fast", "free-exhausted"} <= names)
        self.assertNotIn("free-auto", names, "no fast provider without keys: free-auto must be empty")
        self.assertIn({"free-auto": ["free-exhausted"]}, data["router_settings"]["fallbacks"])

    def test_card_required_providers_are_ignored_even_with_a_key(self):
        result, config = render({"MISTRAL_API_KEY": "x", "OPENROUTER_API_KEY": "x", "CEREBRAS_API_KEY": "x"})
        self.assertEqual(result.returncode, 0, result.stderr)
        text = config.read_text(encoding="utf-8")
        for name in ("mistral", "openrouter", "cerebras"):
            self.assertNotIn(name, text.lower().replace("ignores", ""))

    def test_no_secret_value_in_output(self):
        result, config = render({"GROQ_API_KEY": "SECRET-VALUE-123"})
        self.assertNotIn("SECRET-VALUE-123", config.read_text(encoding="utf-8"))
        self.assertNotIn("SECRET-VALUE-123", result.stdout)

    def test_registry_is_valid(self):
        registry = yaml.safe_load((ROOT / "scripts" / "providers.yaml").read_text(encoding="utf-8"))["fournisseurs"]
        for entry in registry:
            self.assertTrue(entry["cles"] and entry["nom"])
        self.assertEqual({f["nom"] for f in registry if f.get("necessite_carte")}, {"cerebras", "openrouter", "mistral"})
        gh = next(f for f in registry if f["nom"] == "github-models")
        self.assertEqual(gh["cles"], ["GITHUB_MODELS_TOKEN"])


if __name__ == "__main__":
    unittest.main()
