"""Tests du banc de qualite (Q1) : chaque verificateur accepte une bonne reponse et refuse une mauvaise.
Aucun appel reseau : les reponses sont simulees.
Lancer : python -m unittest discover tests -v
"""
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
import qualite as q  # noqa: E402

BONS = {
    "somme": ("```python\ndef somme(a):\n    return sum(a)\n```", q.verif_somme),
    "double": ("```javascript\nfunction double(n) { return n * 2; }\n```", q.verif_double),
    "test_pair": ("```python\ndef test_est_pair():\n    assert est_pair(2)\n    assert not est_pair(3)\n```",
                  q.verif_test_pair),
    "test_unittest": ("```python\nimport unittest\nclass T(unittest.TestCase):\n"
                      "    def test_ajoute(self):\n        self.assertEqual(ajoute(1, 2), 3)\n```",
                      q.verif_test_unittest),
    "keyerror": ("KeyError signifie que la cle est absente du dictionnaire. "
                 "Verifiez avec in ou utilisez get.", q.verif_keyerror),
    "typeerror": ("TypeError : on concatene un int a un str. Convertissez avec str() ou int().",
                  q.verif_typeerror),
    "yaml": ("```yaml\nnom: demo\ndebug: true\nport: 8000\n```", q.verif_yaml),
    "json": ("```json\n{\"nom\": \"demo\", \"port\": 8080}\n```", q.verif_json),
    "div": ("```python\ndef div(a, b):\n    if b == 0:\n        return None\n    return a / b\n```",
            q.verif_div),
    "join": ("```python\ndef f():\n    return \"\".join(str(x) for x in [1, 2, 3])\n```", q.verif_join),
    "raises": ("```python\nimport pytest\ndef test_div_zero():\n    with pytest.raises(ValueError):\n"
               "        div(1, 0)\n```", q.verif_pytest_raises),
    "http": ("404 signifie que la ressource est introuvable cote client. 500 est une erreur serveur.",
             q.verif_http),
    "renomme": ("```python\ndef total(a):\n    resultat = sum(a)\n    return resultat * 2\n```",
                q.verif_renomme),
    "mots": ("```python\ndef compte_mots(texte):\n    return len(texte.split())\n```",
             q.verif_compte_mots),
    "pal": ("```python\ndef est_palindrome(s):\n    s = s.replace(\" \", \"\").lower()\n"
            "    return s == s[::-1]\n```", q.verif_palindrome),
}


class VerificateursTest(unittest.TestCase):
    def test_quinze_taches(self):
        self.assertEqual(len(q.TACHES), 15)
        self.assertEqual(len(BONS), 15)

    def test_bonnes_reponses(self):
        for nom, (texte, verif) in BONS.items():
            with self.subTest(tache=nom):
                self.assertTrue(verif(texte))

    def test_mauvaises_reponses(self):
        for nom, (_, verif) in BONS.items():
            with self.subTest(tache=nom):
                self.assertFalse(verif("Je ne sais pas."))


if __name__ == "__main__":
    unittest.main()
