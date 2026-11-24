"""Tests de l'orchestrateur « un seul agent » et du pont de compétences."""
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "orchestrateur"))

import classeur  # noqa: E402
import competences  # noqa: E402
import agent  # noqa: E402


def msg(role, content):
    return {"role": role, "content": content}


class ClasseurTest(unittest.TestCase):
    def test_indice_respecte(self):
        self.assertEqual(classeur.choisir_groupe([], indice="free-code"), "free-code")

    def test_indice_invalide_ignore(self):
        self.assertNotEqual(classeur.choisir_groupe([msg("user", "salut")], indice="n'importe"), "n'importe")

    def test_verification_va_en_free_check(self):
        g = classeur.choisir_groupe([msg("user", "Peux-tu relire et vérifier ce code ?")])
        self.assertEqual(g, "free-check")

    def test_grosse_demande_va_en_free_auto(self):
        gros = msg("user", "x" * (classeur.SEUIL_GROS_TOKENS * 4 + 10))
        self.assertEqual(classeur.choisir_groupe([gros]), "free-auto")

    def test_code_va_en_free_code(self):
        g = classeur.choisir_groupe([msg("user", "Corrige ce bug dans la fonction de login")])
        self.assertEqual(g, "free-code")

    def test_petite_question(self):
        g = classeur.choisir_groupe([msg("user", "Quelle est la capitale du Congo ?")])
        self.assertEqual(g, "free-question")

    def test_estimer_tokens(self):
        self.assertEqual(classeur.estimer_tokens([msg("user", "a" * 40)]), 10)


class CompetencesTest(unittest.TestCase):
    def test_charger_et_selectionner(self):
        dossier = RACINE / "orchestrateur" / "competences-exemple"
        comps = competences.charger_competences(dossier)
        self.assertTrue(any(c["nom"] == "revue-securite" for c in comps))
        choisies = competences.selectionner(comps, "fais une revue de sécurité du code")
        self.assertTrue(choisies)
        self.assertEqual(choisies[0]["nom"], "revue-securite")

    def test_selection_vide_si_hors_sujet(self):
        comps = competences.charger_competences(RACINE / "orchestrateur" / "competences-exemple")
        self.assertEqual(competences.selectionner(comps, "recette de cuisine"), [])

    def test_frontmatter_et_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "ma-competence"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nnom: demo\ndescription: une demo\n---\nCorps de la compétence.",
                encoding="utf-8",
            )
            comps = competences.charger_competences(tmp)
            self.assertEqual(comps[0]["nom"], "demo")
            self.assertEqual(comps[0]["corps"], "Corps de la compétence.")
            prompt = competences.construire_prompt_systeme(comps, base="Persona.")
            self.assertIn("Persona.", prompt)
            self.assertIn("Corps de la compétence.", prompt)


class AgentTest(unittest.TestCase):
    def test_preparer_requete_route_et_injecte(self):
        dossier = RACINE / "orchestrateur" / "competences-exemple"
        payload = {"messages": [msg("user", "Peux-tu faire une revue de sécurité de ce code ?")]}
        prep = agent.preparer_requete(payload, dossier_competences=dossier, persona="Persona.")
        # relecture → free-check
        self.assertEqual(prep["model"], "free-check")
        # un message système en tête, contenant persona + compétence
        self.assertEqual(prep["messages"][0]["role"], "system")
        self.assertIn("Persona.", prep["messages"][0]["content"])
        self.assertIn("revue-securite", prep["messages"][0]["content"])

    def test_preparer_requete_remplace_systeme_existant(self):
        payload = {"messages": [msg("system", "ancien"), msg("user", "une petite question ?")]}
        prep = agent.preparer_requete(payload, persona="Nouvelle persona.")
        systemes = [m for m in prep["messages"] if m["role"] == "system"]
        self.assertEqual(len(systemes), 1)
        self.assertNotIn("ancien", systemes[0]["content"])


if __name__ == "__main__":
    unittest.main()
