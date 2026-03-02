# GraphML Conversion Suite

Ensemble d'outils Python pour convertir des fichiers GraphML (créés avec yEd) vers différents formats : SVG, JPG, Mermaid et analyse visuelle.

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-green.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Table des matières

- [À propos du projet](#à-propos-du-projet)
- [Fonctionnalités](#fonctionnalités)
- [Structure du projet](#structure-du-projet)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Utilisation](#utilisation)
  - [GraphML vers SVG](#graphml-vers-svg)
  - [GraphML vers JPG](#graphml-vers-jpg)
  - [GraphML vers Mermaid](#graphml-vers-mermaid)
- [Exemples](#exemples)
- [Contribution](#contribution)
- [Licence](#licence)

## À propos du projet

Ce projet fournit une suite d'outils pour transformer des diagrammes yEd (au format GraphML) en différents formats exploitables :

- **SVG** : Format vectoriel préservant la qualité à tout zoom
- **JPG** : Image raster pour une visualisation directe et un partage facile
- **Mermaid** : Format Markdown avec diagrammes interactifs pour GitHub/GitLab

### Caractéristiques principales

- ✅ Préservation complète de la structure du graphe
- ✅ Gestion des nœuds, arêtes et groupes
- ✅ Support des labels d'arêtes avec positionnement intelligent
- ✅ Extraction des styles (couleurs, fonts, types de lignes)
- ✅ Analyse visuelle détaillée en JPG
- ✅ Export Mermaid compatible GitHub

## Fonctionnalités

### graphmlcore.py
Bibliothèque centrale fournissant :
- Parsing XML des fichiers GraphML yEd
- Définitions de types pour structures GraphML
- Calculs de géométrie (chemins, labels, limites)
- Fonctions utilitaires (couleurs, fonts, styles)

### graphml2svg.py
Convertit GraphML en SVG vectoriel :
- Préservation de tous les éléments visuels
- Labels d'arêtes positionnés intelligemment
- Flèches directionnelles automatiques
- Support des formes complexes et SVG embarqués

### graphml2jpg.py
Génère une visualisation JPG avec analyse complète :
- Image haute résolution avec grille
- Affichage des coordonnées exactes
- Positions des labels d'arêtes
- Analyse détaillée de la structure

### graphml2mermaid.py
Exporte en format Mermaid (Markdown) :
- Diagrammes interactifs
- Support des groupes/subgraphes
- Styles CSS intégrés
- Compatible GitHub/GitLab

## Structure du projet

```
test2/
├── graphmlcore.py           # Bibliothèque core
├── graphml2svg.py           # Convertisseur SVG
├── graphml2jpg.py           # Convertisseur JPG (analyse visuelle)
├── graphml2mermaid.py       # Convertisseur Mermaid
├── README.md                # Ce fichier
├── LICENSE                  # Licence GPLv3
└── graphml/                 # Exemples de fichiers GraphML
    ├── simple1.graphml
    ├── simple2.graphml
    └── ...
└── target/                  # Dossier de sortie
    ├── simple1.svg
    ├── simple1.jpg
    ├── simple1.md
    └── ...
```

## Prérequis

- Python 3.7+
- Pillow (PIL) pour le traitement d'images JPG
- ElementTree (inclus dans Python)

## Installation

### 1. Cloner le repository

### 2. Installer les dépendances

```bash
pip install Pillow
```

C'est tout ! Les autres modules (`xml`, `re`, `math`) sont intégrés à Python.

### Vérification

Testez que tout fonctionne :

```bash
python -c "from graphmlcore import parse_graphml; print('✓ graphmlcore OK')"
python -c "import graphml2svg; print('✓ graphml2svg OK')"
python -c "import graphml2jpg; print('✓ graphml2jpg OK')"
python -c "import graphml2mermaid; print('✓ graphml2mermaid OK')"
```

## Utilisation

### GraphML vers SVG

Convertir un fichier GraphML en SVG vectoriel :

```bash
python graphml2svg.py <input.graphml> <output.svg>
```

**Exemple :**
```bash
python graphml2svg.py ./graphml/simple1.graphml ./target/simple1.svg
```

**Résultat :** Un fichier SVG avec tous les nœuds, arêtes et labels préservés.

---

### GraphML vers JPG

Générer une image JPG avec analyse visuelle détaillée :

```bash
python graphml2jpg.py
```

Le script utilise les fichiers définis dans sa fonction `main()` :

```python
if __name__ == '__main__':
    visualizer = ImprovedGraphMLVisualizer('./graphml/simple1.graphml', scale=2.5)
    visualizer.parse()
    visualizer.draw_to_image('./target/simple1.jpg')
```

**Personnalisation :**

Modifiez le script pour vos fichiers ou appelez directement :

```python
from graphml2jpg import ImprovedGraphMLVisualizer

visualizer = ImprovedGraphMLVisualizer('./graphml/votre_fichier.graphml', scale=2.5)
visualizer.parse()
visualizer.draw_to_image('./target/votre_fichier.jpg')
```

**Résultat :** Une image JPG haute résolution avec :
- Grille de référence
- Coordonnées exactes des éléments
- Analyse des positions des labels
- Visualisation complète du graphe

---

### GraphML vers Mermaid

Convertir en diagramme Mermaid (format Markdown) :

```bash
python graphml2mermaid.py <input.graphml> <output.md> [direction]
```

**Paramètres :**
- `input.graphml` : Fichier source
- `output.md` : Fichier Markdown cible
- `direction` (optionnel) : `TD` (haut-bas), `LR` (gauche-droite), `BT` (bas-haut), `RL` (droite-gauche)

**Exemples :**

```bash
# Direction par défaut (Top-Down)
python graphml2mermaid.py ./graphml/simple1.graphml ./target/simple1.md

# Direction gauche-droite
python graphml2mermaid.py ./graphml/simple1.graphml ./target/simple1.md LR

# Direction bas-haut
python graphml2mermaid.py ./graphml/simple1.graphml ./target/simple1.md BT
```

**Résultat :** Un fichier Markdown contenant :
```markdown
# simple1

**Diagram Type:** Mermaid (LR)
**Nodes:** 5 | **Groups:** 2 | **Edges:** 6

\`\`\`mermaid
graph LR
    subgraph group1["Groupe 1"]
        nodeA["Node A"]
        nodeB["Node B"]
    end
    nodeA -->|"Label"| nodeB
\`\`\`
```

## Exemples

### Exemple 1 : Workflow complet

Convertir `simple1.graphml` en tous les formats :

```bash
# SVG (vectoriel)
python graphml2svg.py ./graphml/simple1.graphml ./target/simple1.svg

# JPG (image avec analyse)
python graphml2jpg.py  # Modifiez le path dans le script

# Mermaid (Markdown interactif)
python graphml2mermaid.py ./graphml/simple1.graphml ./target/simple1.md LR
```

### Exemple 2 : Utilisation en Python

```python
from graphmlcore import parse_graphml

# Parser un fichier GraphML
data = parse_graphml('./graphml/simple1.graphml')

# Accéder aux données
print(f"Nœuds : {len(data['nodes'])}")
print(f"Arêtes : {len(data['edges'])}")
print(f"Groupes : {len(data['groups'])}")

# Afficher les informations de chaque nœud
for node in data['nodes']:
    print(f"  - {node['id']}: {node.get('label', '(sans label)')}")
```

### Exemple 3 : Génération SVG personnalisée

```python
from graphmlcore import parse_graphml
from graphml2svg import build_svg_structure, convert

# Convertir
convert('./graphml/simple1.graphml', './target/simple1.svg')

# Ou accéder aux données brutes
data = parse_graphml('./graphml/simple1.graphml')
# ... traiter les données ...
```

## Architecture

### Flux de traitement

```
GraphML (yEd)
    ↓
parse_graphml() [graphmlcore]
    ↓
{nodes, edges, groups, labels, styles}
    ↓
    ├─→ build_svg_structure() → SVG
    ├─→ draw_to_image() → JPG
    └─→ generate_mermaid_code() → Mermaid
```

### Types de données principaux

- **Geometry** : Position (x, y) et dimensions (width, height)
- **EdgeLabel** : Label d'arête avec positionnement intelligent
- **EdgePath** : Points du chemin d'une arête
- **EdgeGeometry** : Géométrie complète d'une arête

## Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. **Fork** le projet
2. **Créez une branche** pour votre fonctionnalité (`git checkout -b feature/MaFonctionnalite`)
3. **Committez** vos changements (`git commit -m 'Ajoute MaFonctionnalite'`)
4. **Poussez** vers la branche (`git push origin feature/MaFonctionnalite`)
5. **Ouvrez une Pull Request**

### Idées pour contribuer

- Support de nouveaux formats (PNG, PDF, etc.)
- Amélioration des styles et thèmes
- Documentation et exemples supplémentaires
- Optimisation des performances

## Licence

Ce projet est distribué sous la **Licence Publique Générale GNU v3.0 (GPLv3)**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

### Résumé GPLv3

- ✅ **Utilisation libre** pour tout usage
- ✅ **Modification libre** du code source
- ✅ **Distribution libre**, même commerciale
- ⚖️ **Obligation** : Distribuer sous la même licence GPLv3
- ⚖️ **Obligation** : Inclure le code source et la licence
- ⚖️ **Obligation** : Documenter les modifications apportées

Pour plus d'informations : https://www.gnu.org/licenses/gpl-3.0.html

---

## Support

Pour toute question ou problème :

1. Consultez la [documentation du code](graphmlcore.py)
2. Vérifiez les exemples dans le dossier `graphml/`
3. Testez avec un fichier GraphML simple d'abord

## Remerciements

- **yEd** pour le format GraphML robuste
- **Mermaid** pour le rendu de diagrammes interactifs
- **Pillow** pour le traitement d'images
- **ElementTree** pour le parsing XML

---

**Dernière mise à jour** : 2026-02-27  
**Version** : 1.0.0
