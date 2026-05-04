import unittest

from seed_data import (
    REFERENCE_MEASURES,
    attach_measure_ids_to_capteurs,
    generate_citizen_rows,
    generate_live_measure_row,
    generate_measure_and_capteur_rows,
    generate_measure_rows,
    generate_standalone_measure_rows,
    generate_vehicle_rows,
)


class StreamlitSeedTests(unittest.TestCase):
    def test_hors_service_reference_measure_has_no_value(self) -> None:
        self.assertIsNone(REFERENCE_MEASURES[4][0])

    def test_hors_service_sensor_does_not_generate_measure_rows(self) -> None:
        rows, current_links = generate_measure_rows(
            [
                (1, "pollution", "actif"),
                (2, "pollution", "hors service"),
            ],
            per_sensor=2,
            step_minutes=30,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(current_links, [(1, 0)])

    def test_bulk_generators_return_requested_count(self) -> None:
        self.assertEqual(len(generate_citizen_rows(100)), 100)
        self.assertEqual(len(generate_vehicle_rows(100)), 100)
        self.assertEqual(len(generate_standalone_measure_rows(100)), 100)

    def test_capteur_bulk_generation_matches_measure_count(self) -> None:
        measure_rows, capteur_rows = generate_measure_and_capteur_rows(100)
        attached_rows = attach_measure_ids_to_capteurs(capteur_rows, list(range(1, 101)))

        self.assertEqual(len(measure_rows), 100)
        self.assertEqual(len(capteur_rows), 100)
        self.assertEqual(len(attached_rows), 100)
        self.assertEqual(attached_rows[0][-1], 1)

    def test_live_measure_generation_keeps_temperature_in_range(self) -> None:
        value, unit, measure_type, timestamp = generate_live_measure_row(
            sensor_type="temperature",
            sensor_state="actif",
            current_value=25.0,
        )

        self.assertIsNotNone(value)
        self.assertEqual(unit, "C")
        self.assertEqual(measure_type, "temperature")
        self.assertEqual(timestamp.second, 0)
        self.assertGreaterEqual(value, 14.0)
        self.assertLessEqual(value, 39.0)


if __name__ == "__main__":
    unittest.main()
