import unittest
from datetime import datetime
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from ai_reports import (
    AIProviderConfig,
    build_report_context,
    generate_ai_report,
    load_dotenv_values,
    suggest_actions,
)


def sample_context() -> dict:
    sensors = pd.DataFrame(
        [
            {
                "id_capteur": 1,
                "type_capteur": "pollution",
                "localisation": "Centre Ville Tunis",
                "etat_capteur": "actif",
                "valeur": 112.5,
                "unite": "AQI",
                "type_mesure": "pollution",
                "horodatage": "2026-04-23 08:00:00",
            },
            {
                "id_capteur": 2,
                "type_capteur": "pollution",
                "localisation": "Monastir Centre",
                "etat_capteur": "hors service",
                "valeur": None,
                "unite": "AQI",
                "type_mesure": "pollution",
                "horodatage": "2026-04-23 09:00:00",
            },
            {
                "id_capteur": 3,
                "type_capteur": "humidite",
                "localisation": "Sousse Corniche",
                "etat_capteur": "signale",
                "valeur": 70.0,
                "unite": "%",
                "type_mesure": "humidite",
                "horodatage": "2026-04-23 10:00:00",
            },
        ]
    )
    interventions = pd.DataFrame(
        [
            {
                "id_intervention": 1,
                "statut_intervention": "en_cours",
                "id_capteur": 2,
                "localisation": "Monastir Centre",
            },
            {
                "id_intervention": 2,
                "statut_intervention": "terminee",
                "id_capteur": 3,
                "localisation": "Sousse Corniche",
            },
        ]
    )
    top_polluted_zones = pd.DataFrame(
        [
            {
                "localisation": "Centre Ville Tunis",
                "moyenne_pollution": 112.5,
                "nombre_mesures": 12,
            },
            {
                "localisation": "Monastir Centre",
                "moyenne_pollution": 84.2,
                "nombre_mesures": 5,
            },
        ]
    )
    return build_report_context(
        sensors,
        interventions,
        top_polluted_zones,
        generated_at=datetime(2026, 4, 25, 10, 0, 0),
    )


class AIReportTests(unittest.TestCase):
    def test_context_counts_operational_risks(self) -> None:
        context = sample_context()

        self.assertEqual(context["counts"]["capteurs"], 3)
        self.assertEqual(context["counts"]["capteurs_hors_service"], 1)
        self.assertEqual(context["counts"]["capteurs_signales"], 1)
        self.assertEqual(context["counts"]["mesures_sans_valeur"], 1)
        self.assertEqual(context["counts"]["zones_pollution_critique"], 1)

    def test_suggest_actions_prioritizes_critical_pollution(self) -> None:
        actions = suggest_actions(sample_context())

        self.assertEqual(actions[0]["priorite"], "haute")
        self.assertEqual(actions[0]["categorie"], "pollution")

    def test_local_report_mentions_key_counts_and_actions(self) -> None:
        result = generate_ai_report(sample_context(), AIProviderConfig())

        self.assertEqual(result["source"], "local")
        self.assertIn("3 capteurs suivis", result["report"])
        self.assertIn("Actions recommandees", result["report"])
        self.assertGreaterEqual(len(result["actions"]), 4)

    def test_no_risk_context_gets_normal_surveillance_action(self) -> None:
        sensors = pd.DataFrame(
            [
                {
                    "id_capteur": 1,
                    "etat_capteur": "actif",
                    "valeur": 42.0,
                    "localisation": "Tunis",
                }
            ]
        )
        context = build_report_context(
            sensors,
            pd.DataFrame(),
            pd.DataFrame(),
            generated_at=datetime(2026, 4, 25, 10, 0, 0),
        )

        actions = suggest_actions(context)

        self.assertEqual(actions, [{
            "priorite": "basse",
            "categorie": "exploitation",
            "action": "Maintenir la surveillance normale; aucune anomalie prioritaire detectee.",
        }])

    @patch("ai_reports.generate_remote_report", side_effect=TimeoutError("timeout"))
    def test_remote_failure_falls_back_to_local_report(self, _remote) -> None:
        config = AIProviderConfig(
            api_key="secret",
            base_url="https://example.test/v1",
            model="kimi-k2.6",
        )

        result = generate_ai_report(sample_context(), config)

        self.assertEqual(result["source"], "local")
        self.assertIn("timeout", result["error"])

    @patch("ai_reports.generate_remote_report", return_value="Rapport distant valide")
    def test_remote_report_is_used_when_provider_succeeds(self, _remote) -> None:
        config = AIProviderConfig(api_key="secret")

        result = generate_ai_report(sample_context(), config)

        self.assertEqual(result["source"], "meta-llama/Llama-3.1-8B-Instruct:novita")
        self.assertEqual(result["report"], "Rapport distant valide")

    def test_disallowed_provider_url_scheme_falls_back_to_local_report(self) -> None:
        config = AIProviderConfig(
            api_key="secret",
            base_url="file:///tmp/report",
            model="unsafe-demo",
        )

        result = generate_ai_report(sample_context(), config)

        self.assertEqual(result["source"], "local")
        self.assertIn("scheme non autorise", result["error"])

    def test_dotenv_lama_apikey_configures_hugging_face_defaults(self) -> None:
        with TemporaryDirectory() as tempdir:
            env_path = Path(tempdir) / ".env"
            env_path.write_text("lama_apikey=hf_test_token\n", encoding="utf-8")

            with patch.dict(
                environ,
                {
                    "AI_REPORT_API_KEY": "",
                    "HF_TOKEN": "",
                    "HUGGINGFACEHUB_API_TOKEN": "",
                    "lama_apikey": "",
                    "LLAMA_APIKEY": "",
                    "AI_REPORT_BASE_URL": "",
                    "AI_REPORT_MODEL": "",
                    "HF_REPORT_MODEL": "",
                },
                clear=False,
            ), patch("ai_reports.DOTENV_PATH", env_path):
                config = AIProviderConfig.from_env()

        self.assertEqual(config.api_key, "hf_test_token")
        self.assertEqual(config.base_url, "https://router.huggingface.co/v1")
        self.assertEqual(config.model, "meta-llama/Llama-3.1-8B-Instruct:novita")

    def test_dotenv_parser_handles_quotes(self) -> None:
        with TemporaryDirectory() as tempdir:
            env_path = Path(tempdir) / ".env"
            env_path.write_text('lama_apikey="hf_test_token"\n', encoding="utf-8")

            self.assertEqual(load_dotenv_values(env_path)["lama_apikey"], "hf_test_token")


if __name__ == "__main__":
    unittest.main()
