DROP DATABASE IF EXISTS compcodex_db;

CREATE DATABASE IF NOT EXISTS compcodex_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE compcodex_db;

CREATE TABLE IF NOT EXISTS citoyens (
  id_citoyen INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nom VARCHAR(100) NOT NULL,
  prenom VARCHAR(100) NOT NULL,
  adresse VARCHAR(255) NOT NULL,
  telephone VARCHAR(20) NOT NULL,
  PRIMARY KEY (id_citoyen),
  INDEX idx_citoyens_nom (nom),
  INDEX idx_citoyens_adresse (adresse),
  INDEX idx_citoyens_telephone (telephone)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS vehicule (
  id_vehicule INT UNSIGNED NOT NULL AUTO_INCREMENT,
  immatriculation VARCHAR(50) NOT NULL,
  modele VARCHAR(100) NOT NULL,
  etat_vehicule ENUM('stationne', 'en route', 'en panne', 'arrive') NOT NULL,
  date_mise_service DATE NOT NULL,
  PRIMARY KEY (id_vehicule),
  UNIQUE KEY uq_vehicule_immatriculation (immatriculation),
  INDEX idx_vehicule_etat (etat_vehicule),
  INDEX idx_vehicule_date_service (date_mise_service)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS mesure (
  id_mesure INT UNSIGNED NOT NULL AUTO_INCREMENT,
  valeur DECIMAL(10,2) NULL,
  unite VARCHAR(30) NOT NULL,
  type_mesure VARCHAR(100) NOT NULL,
  horodatage DATETIME NOT NULL,
  PRIMARY KEY (id_mesure),
  INDEX idx_mesure_type (type_mesure),
  INDEX idx_mesure_horodatage (horodatage),
  INDEX idx_mesure_valeur (valeur)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS capteur (
  id_capteur INT UNSIGNED NOT NULL AUTO_INCREMENT,
  type_capteur VARCHAR(100) NOT NULL,
  localisation VARCHAR(255) NOT NULL,
  date_installation DATE NOT NULL,
  etat_capteur ENUM('inactif', 'actif', 'signale', 'en maintenance', 'hors service') NOT NULL,
  id_mesure INT UNSIGNED NOT NULL,
  PRIMARY KEY (id_capteur),
  INDEX idx_capteur_type (type_capteur),
  INDEX idx_capteur_localisation (localisation),
  INDEX idx_capteur_date_installation (date_installation),
  INDEX idx_capteur_etat (etat_capteur),
  INDEX idx_capteur_mesure (id_mesure),
  CONSTRAINT fk_capteur_mesure
    FOREIGN KEY (id_mesure)
    REFERENCES mesure (id_mesure)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS intervention (
  id_intervention INT UNSIGNED NOT NULL AUTO_INCREMENT,
  date_demande DATETIME NOT NULL,
  date_debut DATETIME NULL,
  date_fin DATETIME NULL,
  statut_intervention VARCHAR(50) NOT NULL,
  id_capteur INT UNSIGNED NOT NULL,
  PRIMARY KEY (id_intervention),
  INDEX idx_intervention_statut (statut_intervention),
  INDEX idx_intervention_dates (date_demande, date_debut, date_fin),
  INDEX idx_intervention_capteur (id_capteur),
  CONSTRAINT fk_intervention_capteur
    FOREIGN KEY (id_capteur)
    REFERENCES capteur (id_capteur)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE = InnoDB;
