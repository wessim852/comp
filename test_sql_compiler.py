import unittest

from sql_compiler import FrenchSQLCompiler


class FrenchSQLCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = FrenchSQLCompiler()

    def test_top_polluted_zones(self) -> None:
        self.assertEqual(
            self.compiler.compile("Affiche les 5 zones les plus polluées"),
            "SELECT c.localisation, AVG(m.valeur) AS moyenne_pollution "
            "FROM mesure m "
            "JOIN capteur c ON c.id_mesure = m.id_mesure "
            "WHERE m.type_mesure = 'pollution' "
            "GROUP BY c.localisation "
            "ORDER BY moyenne_pollution DESC "
            "LIMIT 5;",
        )

    def test_count_out_of_service_sensors(self) -> None:
        self.assertEqual(
            self.compiler.compile("Combien de capteurs sont hors service ?"),
            "SELECT COUNT(*) AS nombre_capteur FROM capteur "
            "WHERE etat_capteur = 'hors service';",
        )

    def test_interventions_in_progress(self) -> None:
        self.assertEqual(
            self.compiler.compile(
                "Donne-moi les interventions en cours où statut_intervention = 'en_cours'"
            ),
            "SELECT * FROM intervention WHERE statut_intervention = 'en_cours';",
        )

    def test_measure_filters(self) -> None:
        self.assertEqual(
            self.compiler.compile(
                "Montre les mesures où valeur > 50 et type_mesure = 'pollution'"
            ),
            "SELECT * FROM mesure WHERE valeur > 50 AND type_mesure = 'pollution';",
        )

    def test_citizens_by_address(self) -> None:
        self.assertEqual(
            self.compiler.compile("Liste les citoyens où adresse = 'Sousse'"),
            "SELECT * FROM citoyens WHERE adresse = 'sousse';",
        )

    def test_average_grouped_by_measure_type(self) -> None:
        self.assertEqual(
            self.compiler.compile("Moyenne de valeur des mesures groupé par type_mesure"),
            "SELECT type_mesure, AVG(valeur) AS moyenne_valeur "
            "FROM mesure "
            "GROUP BY type_mesure;",
        )

    def test_sensors_sorted_by_installation_date(self) -> None:
        self.assertEqual(
            self.compiler.compile(
                "Affiche les capteurs triés par date_installation décroissant"
            ),
            "SELECT * FROM capteur ORDER BY date_installation DESC;",
        )

    def test_vehicle_limit(self) -> None:
        self.assertEqual(
            self.compiler.compile("Affiche les 3 véhicules"),
            "SELECT * FROM vehicule LIMIT 3;",
        )

    def test_phone_between_range(self) -> None:
        self.assertEqual(
            self.compiler.compile(
                "Quels citoyens ont le téléphone entre 20000000 et 29999999"
            ),
            "SELECT * FROM citoyens WHERE telephone BETWEEN 20000000 AND 29999999;",
        )

    def test_finished_interventions(self) -> None:
        self.assertEqual(
            self.compiler.compile("Combien d'interventions sont terminées ?"),
            "SELECT COUNT(*) AS nombre_intervention FROM intervention "
            "WHERE statut_intervention = 'terminee';",
        )

    def test_implicit_name_filter(self) -> None:
        self.assertEqual(
            self.compiler.compile("donner les citoyens qui ont le nom wassim"),
            "SELECT * FROM citoyens WHERE nom = 'wassim';",
        )


if __name__ == "__main__":
    unittest.main()
