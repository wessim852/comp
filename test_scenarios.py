import time
import unittest
from datetime import datetime, timedelta

import pandas as pd

from ai_reports import AIProviderConfig, build_report_context, generate_ai_report
from automata import current_state, detect_sensor_value_alerts, validate_sequence
from sql_compiler import FrenchSQLCompiler


class AssignmentScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = FrenchSQLCompiler()

    def test_scenario_01_top_polluted_zones_query_compiles(self) -> None:
        sql = self.compiler.compile("Affiche les 5 zones les plus polluées")

        self.assertIn("ORDER BY moyenne_pollution DESC", sql)
        self.assertTrue(sql.endswith("LIMIT 5;"))

    def test_scenario_02_interventions_in_progress_query_compiles(self) -> None:
        sql = self.compiler.compile("Quelles interventions sont en cours ?")

        self.assertEqual(
            sql,
            "SELECT * FROM intervention WHERE statut_intervention = 'en_cours';",
        )

    def test_scenario_03_sensor_signal_sequence_reaches_signaled_state(self) -> None:
        result = validate_sequence(
            "capteur",
            ["installation", "détection d'anomalie"],
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.current_state, "signale")

    def test_scenario_04_intervention_full_validation_reaches_done_state(self) -> None:
        state = current_state(
            "intervention",
            ["assigner tech1", "valider tech2", "valider ia", "cloturer"],
        )

        self.assertEqual(state, "termine")

    def test_scenario_05_invalid_vehicle_transition_is_rejected(self) -> None:
        result = validate_sequence("vehicule", ["panne"], initial_state="stationne")

        self.assertFalse(result.valid)
        self.assertIn("Transition invalide", result.errors[0])

    def test_scenario_06_sensor_missing_value_triggers_action(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        alerts = detect_sensor_value_alerts(
            [
                {
                    "id_capteur": 12,
                    "etat_capteur": "actif",
                    "id_mesure": 40,
                    "valeur": None,
                    "horodatage": now - timedelta(minutes=5),
                }
            ],
            now=now,
        )

        self.assertEqual(alerts[0]["code"], "capteur_sans_valeur_1min")

    def test_scenario_07_ai_report_suggests_pollution_action(self) -> None:
        context = build_report_context(
            pd.DataFrame(
                [
                    {
                        "id_capteur": 1,
                        "localisation": "Centre Ville Tunis",
                        "etat_capteur": "actif",
                        "valeur": 120.0,
                    }
                ]
            ),
            pd.DataFrame(),
            pd.DataFrame(
                [
                    {
                        "localisation": "Centre Ville Tunis",
                        "moyenne_pollution": 120.0,
                    }
                ]
            ),
        )

        result = generate_ai_report(context, AIProviderConfig())

        self.assertEqual(result["actions"][0]["categorie"], "pollution")
        self.assertIn("Centre Ville Tunis", result["report"])

    def test_scenario_08_ai_report_suggests_maintenance_action(self) -> None:
        context = build_report_context(
            pd.DataFrame(
                [
                    {
                        "id_capteur": 8,
                        "localisation": "Monastir Centre",
                        "etat_capteur": "hors service",
                        "valeur": None,
                    }
                ]
            ),
            pd.DataFrame(),
            pd.DataFrame(),
        )

        result = generate_ai_report(context, AIProviderConfig())

        categories = {action["categorie"] for action in result["actions"]}
        self.assertIn("capteurs", categories)

    def test_scenario_09_full_pdf_example_flow(self) -> None:
        sensor_state = current_state(
            "capteur",
            ["installation", "detection anomalie"],
        )
        intervention_state = current_state(
            "intervention",
            ["assigner tech1", "valider tech2", "valider ia"],
        )
        sql = self.compiler.compile("Quelles interventions sont en cours ?")
        context = build_report_context(
            pd.DataFrame(
                [
                    {
                        "id_capteur": 21,
                        "localisation": "Sfax Medina",
                        "etat_capteur": sensor_state,
                        "valeur": 91.0,
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "id_intervention": 7,
                        "statut_intervention": "en_cours",
                        "id_capteur": 21,
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "localisation": "Sfax Medina",
                        "moyenne_pollution": 91.0,
                    }
                ]
            ),
        )
        report = generate_ai_report(context, AIProviderConfig())

        self.assertEqual(sensor_state, "signale")
        self.assertEqual(intervention_state, "ia valide")
        self.assertIn("statut_intervention = 'en_cours'", sql)
        self.assertIn("interventions ouvertes", report["report"])

    def test_scenario_10_report_generation_handles_1000_records_quickly(self) -> None:
        records = [
            {
                "id_capteur": index,
                "localisation": f"Zone {index % 20}",
                "etat_capteur": "actif",
                "valeur": 35.0 + (index % 90),
            }
            for index in range(1000)
        ]
        started_at = time.perf_counter()
        context = build_report_context(
            pd.DataFrame(records),
            pd.DataFrame(),
            pd.DataFrame(
                [
                    {
                        "localisation": "Zone 1",
                        "moyenne_pollution": 101.0,
                    }
                ]
            ),
        )
        result = generate_ai_report(context, AIProviderConfig())
        elapsed = time.perf_counter() - started_at

        self.assertEqual(context["counts"]["capteurs"], 1000)
        self.assertLess(elapsed, 1.0)
        self.assertIn("1000 capteurs suivis", result["report"])


if __name__ == "__main__":
    unittest.main()
