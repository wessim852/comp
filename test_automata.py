import unittest
from datetime import datetime, timedelta

from automata import (
    current_state,
    detect_sensor_value_alerts,
    evaluate_actions,
    validate_sequence,
)


class AutomataTests(unittest.TestCase):
    def test_valid_capteur_sequence(self) -> None:
        result = validate_sequence(
            "capteur",
            ["installation", "detection anomalie", "reparation", "reparation"],
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.current_state, "actif")
        self.assertEqual(len(result.history), 4)

    def test_capteur_alias_incatif_initial_state(self) -> None:
        self.assertEqual(
            current_state("capteur", ["installation"], initial_state="incatif"),
            "actif",
        )

    def test_invalid_capteur_sequence(self) -> None:
        result = validate_sequence("capteur", ["panne"], initial_state="inactif")

        self.assertFalse(result.valid)
        self.assertEqual(result.current_state, "inactif")
        self.assertIn("Transition invalide", result.errors[0])

    def test_valid_intervention_sequence(self) -> None:
        self.assertEqual(
            current_state(
                "intervention",
                ["assigner tech1", "valider tech2", "valider ia", "cloturer"],
            ),
            "termine",
        )

    def test_valid_vehicule_sequence(self) -> None:
        self.assertEqual(
            current_state(
                "vehicule",
                ["demarrer", "panne", "reparer", "arrive", "stationne"],
            ),
            "stationne",
        )

    def test_current_state_raises_on_invalid_sequence(self) -> None:
        with self.assertRaises(ValueError):
            current_state("vehicule", ["panne"], initial_state="stationne")

    def test_capteur_hors_service_alert_after_24h(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = evaluate_actions(
            "capteur",
            "hors service",
            entered_at=now - timedelta(hours=25),
            now=now,
        )

        self.assertEqual(actions[0]["code"], "capteur_hors_service_24h")

    def test_capteur_hors_service_alert_not_before_24h(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = evaluate_actions(
            "capteur",
            "hors service",
            entered_at=now - timedelta(hours=23, minutes=59),
            now=now,
        )

        self.assertEqual(actions, [])

    def test_no_capteur_alert_when_state_is_not_hors_service(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = evaluate_actions(
            "capteur",
            "actif",
            entered_at=now - timedelta(hours=48),
            now=now,
        )

        self.assertEqual(actions, [])

    def test_sensor_without_value_alert_after_one_minute(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = detect_sensor_value_alerts(
            [
                {
                    "id_capteur": 5,
                    "etat_capteur": "hors service",
                    "id_mesure": 5,
                    "valeur": None,
                    "horodatage": now - timedelta(minutes=2),
                }
            ],
            now=now,
            threshold=timedelta(minutes=1),
        )

        self.assertEqual(actions[0]["code"], "capteur_sans_valeur_1min")

    def test_sensor_without_value_no_alert_before_one_minute(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = detect_sensor_value_alerts(
            [
                {
                    "id_capteur": 5,
                    "etat_capteur": "hors service",
                    "id_mesure": 5,
                    "valeur": None,
                    "horodatage": now - timedelta(seconds=30),
                }
            ],
            now=now,
            threshold=timedelta(minutes=1),
        )

        self.assertEqual(actions, [])

    def test_active_sensor_with_recent_value_has_no_alert(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = detect_sensor_value_alerts(
            [
                {
                    "id_capteur": 1,
                    "etat_capteur": "actif",
                    "id_mesure": 1,
                    "valeur": 42.0,
                    "horodatage": now - timedelta(minutes=5),
                }
            ],
            now=now,
            threshold=timedelta(minutes=1),
        )

        self.assertEqual(actions, [])

    def test_active_sensor_without_value_alert_after_one_minute(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        actions = detect_sensor_value_alerts(
            [
                {
                    "id_capteur": 2,
                    "etat_capteur": "actif",
                    "id_mesure": 2,
                    "valeur": None,
                    "horodatage": now - timedelta(minutes=2),
                }
            ],
            now=now,
            threshold=timedelta(minutes=1),
        )

        self.assertEqual(actions[0]["id_capteur"], 2)


if __name__ == "__main__":
    unittest.main()
