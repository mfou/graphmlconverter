#!/usr/bin/env python3
"""Transform yEd GraphML to SVG"""

import xml.etree.ElementTree as ET
import math
import html.parser
import re
from typing import Dict, List, Any, TypedDict, Tuple

# Import core functions and types from graphmlcore
from graphmlcore import (
    parse_graphml,
    calculate_edges_labels_bounds,
    build_edge_path,
    calculate_path_segment_lengths,
    find_position_on_path,
    calculate_perpendicular_offset,
    build_rounded_path,
    create_arrow_path,
    convert_hex_color_to_rgba,
    map_font_family,
    get_font_style_attributes,
    get_text_anchor,
    get_line_style_attributes,
    clean_embedded_svg,
    HTMLTableParser,
    parse_html_label,
    NAMESPACES,
    FONT_MAPPING,
    # Types
    Geometry,
    EdgeLabel,
    EdgePath,
    EdgeGeometry,
    LabelPosition,
)

# ═════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - Geometry calculations for edges
# ═════════════════════════════════════════════════════════════════════════════

def get_line_rect_intersection(x1: float, y1: float, x2: float, y2: float, 
                                rect_x: float, rect_y: float,
                                rect_width: float, rect_height: float) -> tuple:
    """
    Calculate intersection of a line with a rectangle edge.
    
    Args:
        x1, y1: Start point of line
        x2, y2: End point of line (target inside or on the rectangle)
        rect_x, rect_y: Top-left corner of rectangle
        rect_width, rect_height: Dimensions of rectangle
    
    Returns:
        (x, y) tuple of intersection point on rectangle edge
    """
    # Rectangle bounds
    left = rect_x
    right = rect_x + rect_width
    top = rect_y
    bottom = rect_y + rect_height
    
    # Direction vector
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return (x2, y2)
    
    # Check intersection with each edge
    t_min = float('inf')
    intersection_point = (x2, y2)
    
    # Check right edge
    if dx != 0:
        t = (right - x1) / dx
        if 0 <= t <= 1:
            y = y1 + t * dy
            if top <= y <= bottom and t < t_min:
                t_min = t
                intersection_point = (right, y)
    
    # Check left edge
    if dx != 0:
        t = (left - x1) / dx
        if 0 <= t <= 1:
            y = y1 + t * dy
            if top <= y <= bottom and t < t_min:
                t_min = t
                intersection_point = (left, y)
    
    # Check bottom edge
    if dy != 0:
        t = (bottom - y1) / dy
        if 0 <= t <= 1:
            x = x1 + t * dx
            if left <= x <= right and t < t_min:
                t_min = t
                intersection_point = (x, bottom)
    
    # Check top edge
    if dy != 0:
        t = (top - y1) / dy
        if 0 <= t <= 1:
            x = x1 + t * dx
            if left <= x <= right and t < t_min:
                t_min = t
                intersection_point = (x, top)
    
    return intersection_point

def get_arrow_direction(x1: float, y1: float, x2: float, y2: float, 
                        rect_x: float, rect_y: float,
                        rect_width: float, rect_height: float) -> tuple:
    """
    Determine which side of the rectangle the line comes from and calculate arrow angle.
    
    Args:
        x1, y1: Start point of line (origin)
        x2, y2: End point of line (inside rectangle, center of node)
        rect_x, rect_y: Top-left corner of rectangle
        rect_width, rect_height: Rectangle dimensions
    
    Returns:
        Tuple of (arrow_x, arrow_y, angle, direction) where:
        - arrow_x, arrow_y: Position on rectangle edge
        - angle: Arrow angle in degrees (direction the arrow TIP points)
        - direction: 'north', 'south', 'east', or 'west'
    """
    # Rectangle bounds
    left = rect_x
    right = rect_x + rect_width
    top = rect_y
    bottom = rect_y + rect_height
    
    # Get intersection point (where line crosses node boundary)
    intersection_x, intersection_y = get_line_rect_intersection(
        x1, y1, x2, y2, rect_x, rect_y, rect_width, rect_height
    )
    
    # Calculate the angle the line makes (from start to end)
    dx = x2 - x1
    dy = y2 - y1
    line_angle_rad = math.atan2(dy, dx)
    line_angle = line_angle_rad * 180 / math.pi
    
    # Arrow angle = reverse of line direction (point back toward source)
    arrow_angle = (line_angle + 180) % 360
    
    # Determine which edge the intersection is on (for debugging)
    tolerance = max(0.5, rect_width * 0.01)
    
    if abs(intersection_y - top) < tolerance:
        direction = 'north'
    elif abs(intersection_y - bottom) < tolerance:
        direction = 'south'
    elif abs(intersection_x - left) < tolerance:
        direction = 'west'
    elif abs(intersection_x - right) < tolerance:
        direction = 'east'
    else:
        direction = 'diagonal'
    
    return (intersection_x, intersection_y, arrow_angle, direction)

# ═════════════════════════════════════════════════════════════════════════════
# EMBEDDED SVG EXTRACTION
# ═════════════════════════════════════════════════════════════════════════════

def extract_svg_bounds(svg_content: str) -> Dict[str, float]:
    """
    Extract bounding box from embedded SVG content.
    
    Args:
        svg_content: SVG content string
    
    Returns:
        Dict with 'x', 'y', 'width', 'height' keys
    """
    import re
    
    # Try to get viewBox first (most reliable)
    viewbox_match = re.search(r'viewBox\s*=\s*["\']([^"\']*)["\']', svg_content)
    if viewbox_match:
        parts = viewbox_match.group(1).split()
        if len(parts) >= 4:
            return {
                'x': float(parts[0]),
                'y': float(parts[1]),
                'width': float(parts[2]),
                'height': float(parts[3])
            }
    
    # Try width and height attributes
    width_match = re.search(r'width\s*=\s*["\']?([0-9.]+)', svg_content)
    height_match = re.search(r'height\s*=\s*["\']?([0-9.]+)', svg_content)
    if width_match and height_match:
        return {
            'x': 0,
            'y': 0,
            'width': float(width_match.group(1)),
            'height': float(height_match.group(1))
        }
    
    # Try to parse rect elements to find bounds
    rect_matches = re.findall(r'<rect[^>]*>', svg_content)
    if rect_matches:
        rects = []
        for rect_str in rect_matches:
            x_match = re.search(r'x\s*=\s*["\']?([0-9.]+)', rect_str)
            y_match = re.search(r'y\s*=\s*["\']?([0-9.]+)', rect_str)
            w_match = re.search(r'width\s*=\s*["\']?([0-9.]+)', rect_str)
            h_match = re.search(r'height\s*=\s*["\']?([0-9.]+)', rect_str)
            
            if x_match and y_match and w_match and h_match:
                rects.append({
                    'x': float(x_match.group(1)),
                    'y': float(y_match.group(1)),
                    'width': float(w_match.group(1)),
                    'height': float(h_match.group(1))
                })
        
        if rects:
            min_x = min(r['x'] for r in rects)
            min_y = min(r['y'] for r in rects)
            max_x = max(r['x'] + r['width'] for r in rects)
            max_y = max(r['y'] + r['height'] for r in rects)
            return {
                'x': min_x,
                'y': min_y,
                'width': max_x - min_x,
                'height': max_y - min_y
            }
    
    # Default fallback
    return {'x': 0, 'y': 0, 'width': 100, 'height': 100}

# ═════════════════════════════════════════════════════════════════════════════
# FONCTIONS DE BAS NIVEAU - Coordinatisation et géométrie
# ═════════════════════════════════════════════════════════════════════════════

def calculate_edge_label_position_from_graphml(
    source_geom: Dict[str, float],
    label_data: Dict[str, Any]
) -> Dict[str, float]:
    """
    Calcule la position d'un EdgeLabel directement à partir des données GraphML.
    
    Cette fonction wrapper combine:
    1. Calcul du centre du nœud source
    2. Extraction des coordonnées relatives du label
    3. Calcul de la position absolue
    
    Args:
        source_geom: Géométrie du nœud source {'x', 'y', 'width', 'height'}
        label_data: Données du label GraphML {'x', 'y', 'width', 'height', ...}
    
    Returns:
        Dict avec position absolue {'x', 'y', 'width', 'height', 'center_x', 'center_y'}
    
    Exemple:
        source_geom = {'x': 118.1, 'y': 83.17, 'width': 33.8, 'height': 65.66}
        label_data = {'x': 69.058, 'y': -9.350, 'width': 24.01, 'height': 18.70}
        Résultat: {'x': 204.1, 'y': 106.6, ...}
    """
    # Calculer le centre du nœud source
    source_center_x = source_geom['x'] + source_geom['width'] / 2
    source_center_y = source_geom['y'] + source_geom['height'] / 2
    
    # Extraire les coordonnées relatives du label
    label_rel_x = label_data.get('x', 0.0)
    label_rel_y = label_data.get('y', 0.0)
    label_width = label_data.get('width', 0.0)
    label_height = label_data.get('height', 0.0)
    
    # Utiliser la fonction simple correcte
    return calculate_edge_label_position_simple(
        source_center_x, source_center_y,
        label_rel_x, label_rel_y,
        label_width, label_height
    )

def calculate_edge_label_position_simple(
    source_center_x: float,
    source_center_y: float,
    label_relative_x: float,
    label_relative_y: float,
    label_width: float,
    label_height: float
) -> Dict[str, float]:
    """
    Calcule la position absolue d'un EdgeLabel de manière SIMPLE et CORRECTE.
    
    PRINCIPE FONDAMENTAL (d'après EDGE_LABELS_ANALYSIS.md):
    - Les EdgeLabels sont positionnés RELATIFS au centre du nœud source
    - Les coordonnées x,y du label dans GraphML sont des OFFSETS relatifs
    - Position absolue = source_center + offset_relatif
    
    Cette approche remplace 200+ lignes de code complexe par une formule simple!
    
    Args:
        source_center_x: Coordonnée X du centre du nœud source
        source_center_y: Coordonnée Y du centre du nœud source
        label_relative_x: Offset X du label (attribut x du EdgeLabel GraphML)
        label_relative_y: Offset Y du label (attribut y du EdgeLabel GraphML)
        label_width: Largeur du label
        label_height: Hauteur du label
    
    Returns:
        Dict avec 'x', 'y', 'width', 'height' en WORLD coordinates
    
    Exemple:
        source_center = (135.0, 116.0)
        label_relative = (69.058, -9.350)
        Résultat: x=204.1, y=106.6 ✓
    """
    # Formule simple et correcte
    label_abs_x = source_center_x + label_relative_x
    label_abs_y = source_center_y + label_relative_y
    
    return {
        'x': label_abs_x,
        'y': label_abs_y,
        'width': label_width,
        'height': label_height,
        'center_x': label_abs_x + label_width / 2,
        'center_y': label_abs_y + label_height / 2
    }

def get_segment_endpoints(segment_index: int, 
                         source_center: Tuple[float, float],
                         target_center: Tuple[float, float],
                         path_points: List[Dict[str, float]],
                         path_sx: float = 0.0,
                         path_sy: float = 0.0,
                         path_tx: float = 0.0,
                         path_ty: float = 0.0,
                         source_node_label_center: Tuple[float, float] = None) -> Tuple[float, float, float, float]:
    """
    Récupère les points de début et fin d'un segment du chemin d'arête.
    
    Indexation des segments:
    - Segment 0: de (source_center + offsets) au premier waypoint
    - Segment 1..N-1: entre waypoints
    - Segment N: du dernier waypoint à (target_center + offsets)
    
    Cas spécial: Si le node label du source se trouve sur le segment 0 (vertical ou horizontal),
    le point de départ du segment devient le centre du node label.
    
    Args:
        segment_index: Index du segment
        source_center: Tuple (x, y) du centre du nœud source
        target_center: Tuple (x, y) du centre du nœud cible
        path_points: Liste des waypoints [{'x': ..., 'y': ...}, ...]
        path_sx, path_sy: Offsets du point de départ (pour la connexion au nœud source)
        path_tx, path_ty: Offsets du point d'arrivée (pour la connexion au nœud cible)
        source_node_label_center: Tuple (x, y) du centre du label du nœud source (absolu)
                                 Utilisé pour le segment 0 si le label chevauche le segment
    
    Returns:
        Tuple (seg_start_x, seg_start_y, seg_end_x, seg_end_y)
    """
    # Calculer les points de début et fin du chemin (avec offsets appliqués)
    path_start = (source_center[0] + path_sx, source_center[1] + path_sy)
    path_end = (target_center[0] + path_tx, target_center[1] + path_ty)
    
    if not path_points:
        # Aucun waypoint: segment 0 va de source à target
        return (path_start[0], path_start[1], path_end[0], path_end[1])
    
    if segment_index == 0:
        # Segment 0: de source à premier waypoint
        # CAS SPECIAL: Si le node label du source se trouve sur ce segment, l'utiliser comme point de départ
        segment_start = path_start
        
        if source_node_label_center is not None:
            seg_end = (path_points[0]['x'], path_points[0]['y'])
            dx = abs(seg_end[0] - path_start[0])
            dy = abs(seg_end[1] - path_start[1])
            
            # Si segment 0 est vertical (dx < 5 pixels de tolérance)
            if dx < 5:
                # Vérifier si le centre du label est proche de la coordonnée X du segment
                if abs(source_node_label_center[0] - path_start[0]) < 5:
                    # Le label se trouve sur le segment vertical, l'utiliser comme point de départ
                    segment_start = source_node_label_center
            
            # Si segment 0 est horizontal (dy < 5 pixels de tolérance)
            elif dy < 5:
                # Vérifier si le centre du label est proche de la coordonnée Y du segment
                if abs(source_node_label_center[1] - path_start[1]) < 5:
                    # Le label se trouve sur le segment horizontal, l'utiliser comme point de départ
                    segment_start = source_node_label_center
        
        return (segment_start[0], segment_start[1], path_points[0]['x'], path_points[0]['y'])
    
    elif segment_index < len(path_points):
        # Segments intermédiaires: entre waypoints
        return (path_points[segment_index - 1]['x'], path_points[segment_index - 1]['y'],
                path_points[segment_index]['x'], path_points[segment_index]['y'])
    
    elif segment_index == len(path_points):
        # Dernier segment: du dernier waypoint à target
        return (path_points[-1]['x'], path_points[-1]['y'], path_end[0], path_end[1])
    
    else:
        # Index invalide: par défaut, utiliser le segment complet
        return (path_start[0], path_start[1], path_end[0], path_end[1])


def calculate_label_position_on_segment(
    segment_index: int,
    ratio: float,
    distance: float,
    source_center: Tuple[float, float],
    target_center: Tuple[float, float],
    path_points: List[Dict[str, float]],
    path_sx: float = 0.0,
    path_sy: float = 0.0,
    path_tx: float = 0.0,
    path_ty: float = 0.0,
    source_node_label_center: Tuple[float, float] = None) -> Tuple[float, float]:
    """
    Calcule la position absolue d'un EdgeLabel using SmartEdgeLabel "safe zone" logic.
    
    LOGIQUE (d'après SmartEdgeLabelModel de yEd):
    La safe zone n'est appliquée QUE sur les segments connectés aux nœuds source/target.
    Pour les segments entre waypoints, utiliser directement les waypoints sans recul.
    
    - Segment 0 (source → premier waypoint): Safe zone avec distance recul au départ
    - Segments intermédiaires (waypoint → waypoint): Pas de safe zone, utiliser directement
    - Dernier segment (dernier waypoint → target): Safe zone avec distance recul à l'arrivée
    
    CAS SPECIAL: Si le node label du source se trouve sur le segment 0 (vertical ou horizontal),
    le point de départ de la safe zone devient le centre du node label.
    
    Args:
        segment_index: Index du segment
        ratio: Position le long du segment (0-1), où 0=début et 1=fin
        distance: Distance de recul depuis les nœuds (default distance du SmartEdgeLabel)
        source_center: Tuple (x, y) du centre du nœud source
        target_center: Tuple (x, y) du centre du nœud cible
        path_points: Liste des waypoints
        path_sx, path_sy, path_tx, path_ty: Offsets des connexions aux nœuds
        source_node_label_center: Tuple (x, y) du centre du label du nœud source (absolu)
    
    Returns:
        Tuple (label_x, label_y) - position absolue du label
    """
    # STEP 1: Récupérer les endpoints du segment
    seg_start_x, seg_start_y, seg_end_x, seg_end_y = get_segment_endpoints(
        segment_index, source_center, target_center, path_points,
        path_sx, path_sy, path_tx, path_ty,
        source_node_label_center
    )
    
    # STEP 2: Calculer la direction normalisée du segment
    dx = seg_end_x - seg_start_x
    dy = seg_end_y - seg_start_y
    seg_length = math.sqrt(dx**2 + dy**2)
    
    if seg_length == 0:
        # Segment de longueur zéro: retourner le point de départ
        return (seg_start_x, seg_start_y)
    
    # Normaliser la direction
    norm_dx = dx / seg_length
    norm_dy = dy / seg_length
    
    # STEP 3: Calculer les limites de la safe zone
    # La safe zone ne s'applique QUE sur les segments connectés aux nœuds
    
    num_segments = len(path_points) + 1 if path_points else 1
    
    # Déterminer si c'est un segment connecté à un nœud
    is_segment_0 = (segment_index == 0)  # Connecté au nœud SOURCE
    is_last_segment = (segment_index == num_segments - 1)  # Connecté au nœud TARGET
    is_intermediate = not (is_segment_0 or is_last_segment)  # Entre deux waypoints
    
    # Calculer P0 et P1 en fonction du type de segment
    if is_intermediate:
        # Segments intermédiaires: pas de recul, utiliser les waypoints directement
        p0_x = seg_start_x
        p0_y = seg_start_y
        p1_x = seg_end_x
        p1_y = seg_end_y
    else:
        # Segments connectés à des nœuds: appliquer le distance recul approprié
        if is_segment_0:
            # Segment 0: recul au départ seulement
            p0_x = seg_start_x + distance * norm_dx
            p0_y = seg_start_y + distance * norm_dy
            p1_x = seg_end_x  # waypoint: pas de recul
            p1_y = seg_end_y
        else:  # is_last_segment
            # Dernier segment: recul à l'arrivée seulement
            p0_x = seg_start_x  # waypoint: pas de recul
            p0_y = seg_start_y
            p1_x = seg_end_x - distance * norm_dx
            p1_y = seg_end_y - distance * norm_dy
    
    # STEP 4: Interpoler au ratio dans la safe zone
    label_x = p0_x + ratio * (p1_x - p0_x)
    label_y = p0_y + ratio * (p1_y - p0_y)
    
    return (label_x, label_y)

def draw_group_nodes(groups: List[Dict[str, Any]], bg_x: float, bg_y: float) -> List[str]:
    """
    Draw group nodes (containers with headers and borders).
    
    Args:
        groups: List of group node dictionaries
        bg_x, bg_y: Background offset coordinates
    
    Returns:
        List of SVG line strings for group nodes
    """
    svg_lines = []
    
    for group in groups:
        if 'geometry' not in group:
            continue
        
        # Skip this group if it should not be drawn (hasColor="false")
        if not group.get('should_draw', True):
            continue
        
        geom = group['geometry']
        
        # Body styling
        body_fill_color = convert_hex_color_to_rgba(group.get('body_fill_color', '#F0F0F0'))
        body_border_color = group.get('body_border_color', '#999999')
        body_border_width = group.get('body_border_width', 1.0)
        body_border_type = group.get('body_border_type', 'line')
        
        # BUGFIX: Respect hasColor attributes
        fill_has_color = group.get('fill_has_color', True)
        border_has_color = group.get('border_has_color', True)
        
        # Header styling
        header_fill_color = convert_hex_color_to_rgba(group.get('header_fill_color', '#CCCCCC'))
        header_height = group.get('header_height', 20.0)
        
        # Get line style attributes for the group border (using body border settings)
        body_line_styles = get_line_style_attributes(body_border_type, body_border_width)
        
        # Build stroke attributes for the group border (only apply if border_has_color is True)
        if border_has_color:
            group_stroke_attrs = f'stroke="{body_border_color}" stroke-width="{body_border_width}"'
            for key, value in body_line_styles.items():
                group_stroke_attrs += f' {key}="{value}"'
        else:
            # No border: use transparent/none stroke
            group_stroke_attrs = 'stroke="none"'
        
        # Calculate position (world coordinates)
        group_x = geom['x']
        group_y = geom['y']
        
        svg_lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision">')
        
        # Draw the group outline rectangle (covers header + body) with rounded corners
        svg_lines.append('      <rect x="{}" y="{}" width="{}" height="{}" fill="none" rx="2" ry="2" {}/>'.format(
            group_x, group_y, geom['width'], geom['height'],
            group_stroke_attrs
        ))
        
        # Draw header rectangle (background color only, no border)
        svg_lines.append('      <rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="none" rx="2" ry="2"/>'.format(
            group_x, group_y, geom['width'], header_height,
            header_fill_color
        ))
        
        # Draw body rectangle (background color only if fill_has_color is True)
        body_y = group_y + header_height
        body_height = geom['height'] - header_height
        # BUGFIX: Only fill if fill_has_color is True, otherwise use transparent fill
        body_fill = body_fill_color if fill_has_color else 'none'
        svg_lines.append('      <rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="none" rx="2" ry="2"/>'.format(
            group_x, body_y, geom['width'], body_height,
            body_fill
        ))
        
        # Draw all group labels if present (usually just header label)
        if 'labels' in group:
            for label in group['labels']:
                font_family = map_font_family(label.get('fontFamily', 'Dialog'))
                font_style, font_weight = get_font_style_attributes(label.get('fontStyle', 'plain'))
                text_anchor = get_text_anchor(label.get('alignment', 'center'))
                
                # Vertical position (centered in header)
                label_y = group_y + header_height / 2 + label.get('fontSize', 12) / 3
                
                # Calculate x position based on alignment
                # A small margin from the edges
                margin = 5
                
                if text_anchor == 'start':  # left alignment
                    label_x = group_x + margin
                elif text_anchor == 'end':  # right alignment
                    label_x = group_x + geom['width'] - margin
                else:  # middle/center alignment
                    label_x = group_x + geom['width'] / 2
                
                # Build text attributes
                text_attrs = f'font-family="{font_family}" font-size="{label.get("fontSize", 12)}" fill="{label.get("textColor", "#000000")}" text-anchor="{text_anchor}" font-style="{font_style}" font-weight="{font_weight}"'
                
                # Add underline decoration if needed
                if label.get('underlined', False):
                    text_attrs += ' text-decoration="underline"'
                
                # Add stroke attribute based on hasLineColor
                if label.get('hasLineColor', False):
                    text_attrs += f' stroke="{label.get("textColor", "#000000")}"'
                else:
                    text_attrs += ' stroke="none"'
                
                svg_lines.append('      <text x="{}" y="{}" {}>'.format(
                    label_x, label_y, text_attrs
                ))
                # escape any special characters in the text content
                svg_lines.append(html.escape(str(label.get('text', ''))))
                svg_lines.append('      </text>')
        
        svg_lines.append('    </g>')
    
    return svg_lines

def draw_html_table_as_svg(rows: List[List[Dict]], x: float, y: float, max_width: float, max_height: float, 
                           font_size: int, text_color: str, bg_color: str = 'none', 
                           border_color: str = 'none', border_width: float = 0.0) -> List[str]:
    """
    Draw an HTML table as SVG elements with default HTML table styling.
    
    Default styling (matching HTML defaults):
    - NO borders (transparent)
    - NO background color (transparent cells)
    - Left-aligned text in cells
    - No header styling (all cells same style)
    
    Supports both cell formats:
    - Old format: {'text': '...', 'is_bold': bool, 'is_italic': bool}
    - New format: {'segments': [{'text': '...', 'is_bold': bool, 'is_italic': bool, 'color': '...'}], 'text': ''}
    
    Args:
        rows: List of rows, each row is a list of cell dicts with 'text', 'is_bold', 'is_italic'
        x, y: Top-left position
        max_width, max_height: Maximum dimensions available
        font_size: Font size for cell text
        text_color: Text color (hex)
        bg_color: Background color for cells (default 'none' = transparent)
        border_color: Border color (default 'none' = no borders)
        border_width: Border line width (default 0.0 = no borders)
    
    Returns:
        List of SVG line strings for the table
    """
    if not rows:
        return []
    
    svg_lines = []
    
    # Helper function to extract text from a cell (supports both old and new formats)
    def get_cell_text(cell: Dict) -> str:
        """Extract concatenated text from cell, supporting both formats."""
        if 'segments' in cell and cell['segments']:
            # New format: segments list
            return ''.join(seg.get('text', '') for seg in cell['segments'] if isinstance(seg, dict))
        elif 'text' in cell:
            # Old format or fallback
            return cell.get('text', '')
        return ''
    
    # Calculate grid dimensions
    num_rows = len(rows)
    num_cols = max(len(row) for row in rows) if rows else 1
    
    # Calculate cell dimensions
    cell_padding = 4
    row_height = font_size + 2 * cell_padding
    
    # Calculate column widths based on content
    col_widths = [0] * num_cols
    for row in rows:
        for col_idx, cell in enumerate(row):
            # Estimate width: ~0.6 chars per pixel at this font size
            cell_text = get_cell_text(cell)
            text_width = len(cell_text) * font_size * 0.6
            col_widths[col_idx] = max(col_widths[col_idx], text_width)
    
    # Adjust column widths to fit in available space
    total_content_width = sum(col_widths) + (num_cols - 1) * 2 * cell_padding
    if total_content_width > max_width - 4 * cell_padding:
        # Scale down proportionally
        scale_factor = (max_width - 4 * cell_padding) / total_content_width if total_content_width > 0 else 1
        col_widths = [w * scale_factor for w in col_widths]
    
    # Add padding to each column
    col_widths = [w + 2 * cell_padding for w in col_widths]
    
    # Calculate total table dimensions
    table_width = sum(col_widths)
    table_height = num_rows * row_height
    
    # Check if table fits
    if table_height > max_height:
        # Reduce row height proportionally
        row_height = max_height / num_rows
    
    # Draw table
    svg_lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision">')
    
    # Draw cells - NO background, NO borders by default
    for row_idx, row in enumerate(rows):
        current_x = x
        
        for col_idx, cell in enumerate(row):
            cell_x = current_x
            cell_y = y + row_idx * row_height
            cell_width = col_widths[col_idx]
            cell_height = row_height
            
            # Draw cell with NO fill and NO stroke (transparent, borderless)
            if bg_color != 'none' or border_color != 'none':
                # Only draw rectangle if custom colors are specified
                svg_lines.append('      <rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="{}" stroke-width="{}"/>'.format(
                    cell_x, cell_y, cell_width, cell_height,
                    bg_color, border_color, border_width
                ))
            
            # Draw cell text - LEFT ALIGNED (not centered)
            text_x = cell_x + cell_padding  # Left-align with padding
            text_y = cell_y + cell_height / 2 + font_size / 3
            
            # Get segments if available (new format), otherwise treat as single segment
            segments = cell.get('segments', [])
            
            if segments:
                # New format: render with styled tspan elements for each segment
                text_attrs = f'font-family="sans-serif" font-size="{font_size}" fill="{text_color}" text-anchor="start" stroke="none"'
                svg_lines.append('      <text x="{}" y="{}" {}>'.format(text_x, text_y, text_attrs))
                
                for segment in segments:
                    if isinstance(segment, dict):
                        seg_text = segment.get('text', '')
                        seg_color = segment.get('color')
                        seg_bold = segment.get('is_bold', False)
                        seg_italic = segment.get('is_italic', False)
                        
                        # Truncate if needed
                        max_chars = int((cell_width - 2 * cell_padding) / (font_size * 0.6))
                        if len(seg_text) > max_chars:
                            seg_text = seg_text[:max(3, max_chars - 2)] + '..'
                        
                        # Build tspan attributes
                        tspan_attrs = ''
                        if seg_color:
                            tspan_attrs += f' fill="{seg_color}"'
                        if seg_bold:
                            tspan_attrs += ' font-weight="bold"'
                        if seg_italic:
                            tspan_attrs += ' font-style="italic"'
                        
                        if tspan_attrs:
                            svg_lines.append(f'        <tspan{tspan_attrs}>{html.escape(seg_text)}</tspan>')
                        else:
                            svg_lines.append(f'        <tspan>{html.escape(seg_text)}</tspan>')
                    else:
                        # String segment (fallback)
                        svg_lines.append(f'        <tspan>{html.escape(str(segment))}</tspan>')
                
                svg_lines.append('      </text>')
            else:
                # Old format: single text element with styling
                font_weight = 'bold' if cell.get('is_bold', False) else 'normal'
                font_style = 'italic' if cell.get('is_italic', False) else 'normal'
                
                text_attrs = f'font-family="sans-serif" font-size="{font_size}" font-style="{font_style}" font-weight="{font_weight}" fill="{text_color}" text-anchor="start" stroke="none"'
                
                cell_text = cell.get('text', '')
                max_chars = int((cell_width - 2 * cell_padding) / (font_size * 0.6))
                if len(cell_text) > max_chars:
                    cell_text = cell_text[:max(3, max_chars - 2)] + '..'
                
                svg_lines.append('      <text x="{}" y="{}" {}>{}</text>'.format(
                    text_x, text_y, text_attrs, html.escape(cell_text)
                ))
            
            current_x += cell_width
    
    svg_lines.append('    </g>')
    
    return svg_lines

def draw_shape_nodes(shape_nodes: List[Dict[str, Any]]) -> List[str]:
    """
    Draw shape nodes with borders, fills, and labels.
    
    Args:
        shape_nodes: List of shape node dictionaries
    
    Returns:
        List of SVG line strings for shape nodes
    """
    svg_lines = []
    
    for shape_node in shape_nodes:
        if 'geometry' not in shape_node:
            continue
        
        geom = shape_node['geometry']
        shape_type = shape_node.get('shape_type', 'rectangle')
        
        # Style attributes
        fill_color = convert_hex_color_to_rgba(shape_node.get('fill_color', '#FFFFFF'))
        border_color = shape_node.get('border_color', '#000000')
        border_width = shape_node.get('border_width', 1.0)
        border_type = shape_node.get('border_type', 'line')
        
        # BUGFIX: Respect hasColor attributes
        fill_has_color = shape_node.get('fill_has_color', True)
        border_has_color = shape_node.get('border_has_color', True)
        
        # Get line style attributes for border
        line_styles = get_line_style_attributes(border_type, border_width)
        
        # Build stroke attributes (only apply fill and stroke if their hasColor is True)
        final_fill = fill_color if fill_has_color else 'none'
        if border_has_color:
            stroke_attrs = f'stroke="{border_color}" stroke-width="{border_width}" fill="{final_fill}"'
            for key, value in line_styles.items():
                stroke_attrs += f' {key}="{value}"'
        else:
            # No border: use transparent stroke
            stroke_attrs = f'stroke="none" fill="{final_fill}"'
        
        # Wrap shape node in a transform group to compensate for parent transform
        # The parent group has transform="matrix(1,0,0,1,-bg_x,-bg_y)" which shifts everything
        # We need to counteract this for absolute positioned shape nodes
        node_x = geom['x']
        node_y = geom['y']
        svg_lines.append('    <g transform="matrix(1,0,0,1,{},{})">'.format(node_x, node_y))
        svg_lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision">')
        
        # Draw shape based on type
        if shape_type == 'rectangle3d':
            # Draw a 3D rectangle effect with white highlight on top/left and darker shade on bottom/right
            # Main rectangle without stroke (stroke will be created by 3D lines)
            # Note: coordinates are now relative to the node's position (we're inside a transform group)
            main_rect_attrs = f'fill="{fill_color}" stroke="none"'
            svg_lines.append('      <rect x="0" y="0" width="{}" height="{}" {}/>'.format(
                geom['width'], geom['height'],
                main_rect_attrs
            ))
            
            # 3D effect: white/light lines on top and left edges
            svg_lines.append('      <line x1="0" y1="0" x2="{}" y2="0" stroke="white" stroke-width="1"/>'.format(
                geom['width'] - 1
            ))
            svg_lines.append('      <line x1="0" y1="0" x2="0" y2="{}" stroke="white" stroke-width="1"/>'.format(
                geom['height'] - 1
            ))
            
            # 3D effect: darker lines on bottom and right edges (darker version of fill color)
            from colorsys import rgb_to_hsv, hsv_to_rgb
            # Convert hex color to RGB for darkening
            hex_color = shape_node.get('fill_color', '#FFFFFF')
            try:
                r = int(hex_color[1:3], 16) / 255.0
                g = int(hex_color[3:5], 16) / 255.0
                b = int(hex_color[5:7], 16) / 255.0
                h, s, v = rgb_to_hsv(r, g, b)
                # Darken by reducing value by 30%
                v = max(0, v - 0.3)
                r_dark, g_dark, b_dark = hsv_to_rgb(h, s, v)
                dark_color = '#{:02x}{:02x}{:02x}'.format(
                    int(r_dark * 255),
                    int(g_dark * 255),
                    int(b_dark * 255)
                )
            except:
                dark_color = '#666666'  # Fallback
            
            svg_lines.append('      <line x1="{}" y1="0" x2="{}" y2="{}" stroke="{}" stroke-width="1"/>'.format(
                geom['width'] - 1, geom['width'] - 1, geom['height'] - 1,
                dark_color
            ))
            svg_lines.append('      <line x1="0" y1="{}" x2="{}" y2="{}" stroke="{}" stroke-width="1"/>'.format(
                geom['height'] - 1, geom['width'] - 1, geom['height'] - 1,
                dark_color
            ))
        elif shape_type == 'roundrectangle':
            # Draw a rounded rectangle
            corner_radius = min(geom['width'], geom['height']) / 10  # Corner radius 10% of smallest dimension
            svg_lines.append('      <rect x="0" y="0" width="{}" height="{}" rx="{}" ry="{}" {}/>'.format(
                geom['width'], geom['height'],
                corner_radius, corner_radius,
                stroke_attrs
            ))
        elif shape_type == 'ellipse' or shape_type == 'circle':
            # Draw an ellipse/circle
            cx = geom['width'] / 2
            cy = geom['height'] / 2
            rx = geom['width'] / 2
            ry = geom['height'] / 2
            svg_lines.append('      <ellipse cx="{}" cy="{}" rx="{}" ry="{}" {}/>'.format(
                cx, cy, rx, ry,
                stroke_attrs
            ))
        elif shape_type == 'diamond':
            # Draw a diamond shape
            # Note: coordinates are now relative to the node's position
            cx = geom['width'] / 2
            cy = geom['height'] / 2
            half_width = geom['width'] / 2
            half_height = geom['height'] / 2
            
            points = [
                (cx, 0),  # top
                (geom['width'], cy),  # right
                (cx, geom['height']),  # bottom
                (0, cy)  # left
            ]
            points_str = ' '.join(f'{x},{y}' for x, y in points)
            svg_lines.append('      <polygon points="{}" {}/>'.format(
                points_str,
                stroke_attrs
            ))
        elif shape_type == 'triangle':
            # Draw a triangle (pointing up)
            # Note: coordinates are now relative to the node's position
            cx = geom['width'] / 2
            points = [
                (cx, 0),  # top
                (geom['width'], geom['height']),  # bottom right
                (0, geom['height'])  # bottom left
            ]
            points_str = ' '.join(f'{x},{y}' for x, y in points)
            svg_lines.append('      <polygon points="{}" {}/>'.format(
                points_str,
                stroke_attrs
            ))
        else:
            # Default to rectangle for unknown types
            svg_lines.append('      <rect x="0" y="0" width="{}" height="{}" {}/>'.format(
                geom['width'], geom['height'],
                stroke_attrs
            ))
        
        # Draw all labels if present (multiple labels allowed)
        if 'labels' in shape_node:
            for label in shape_node['labels']:
                font_family = map_font_family(label.get('fontFamily', 'Dialog'))
                text_anchor = get_text_anchor(label.get('alignment', 'center'))
                font_size = label.get('fontSize', 12)
                
                # Get font style if available
                font_style = 'normal'
                font_weight = 'normal'
                if 'fontStyle' in label:
                    font_style, font_weight = get_font_style_attributes(label.get('fontStyle', 'plain'))
                
                # Check if label contains HTML
                if label.get('text', '').startswith('<'):
                    # Parse HTML content
                    html_data = parse_html_label(label['text'])
                    
                    # Check if it's a table
                    if html_data.get('is_table', False):
                        # Draw HTML table as SVG
                        # Note: coordinates are now relative to the node's position (inside transform group)
                        padding = 6
                        table_x = padding
                        table_y = padding
                        table_width = geom['width'] - 2 * padding
                        table_height = geom['height'] - 2 * padding
                        
                        table_svg = draw_html_table_as_svg(
                            html_data['rows'],
                            table_x, table_y,
                            table_width, table_height,
                            font_size=11,  # Slightly smaller for table
                            text_color=label.get('textColor', '#000000')
                            # Uses default: no borders, no background (transparent)
                        )
                        svg_lines.extend(table_svg)
                    else:
                        # Draw as text lines with potential colored segments
                        text_lines = html_data.get('lines', [])
                        
                        if text_lines:
                            font_size = label.get('fontSize', 12)
                            padding = 8
                            line_height = font_size + 3
                            
                            # Calculate total text height needed (number of lines * line_height)
                            total_text_height = len(text_lines) * line_height - 3
                            
                            # Always center text vertically in the shape
                            # Note: coordinates are now relative to the node's position (inside transform group)
                            start_y = geom['height'] / 2 - total_text_height / 2 + font_size / 2
                            
                            # Position X based on alignment
                            if text_anchor == 'start':
                                label_x = padding
                            elif text_anchor == 'end':
                                label_x = geom['width'] - padding
                            else:
                                label_x = geom['width'] / 2
                            
                            # Draw each line of text (each line may have multiple colored segments)
                            for i, line_segments in enumerate(text_lines[:10]):  # Limit to 10 lines max
                                current_y = start_y + (i * line_height)
                                
                                # Check if line_segments is a list of segments or a single segment dict
                                if not isinstance(line_segments, list):
                                    # Single segment (old format compatibility)
                                    line_segments = [line_segments]
                                
                                # Build text element with tspan for each segment
                                text_attrs = f'font-family="{font_family}" font-size="{font_size}" font-style="{font_style}" font-weight="{font_weight}" text-anchor="{text_anchor}" dominant-baseline="middle" stroke="none"'
                                
                                svg_lines.append('      <text x="{}" y="{}" {}>'.format(
                                    label_x, current_y, text_attrs
                                ))
                                
                                # Render each segment (may have different colors)
                                for segment in line_segments:
                                    if isinstance(segment, dict):
                                        text_content = segment.get('text', '')
                                        color = segment.get('color')  # Color from <font color="...">
                                        is_bold = segment.get('is_bold', False)
                                        is_italic = segment.get('is_italic', False)
                                    else:
                                        # Fallback for string segments
                                        text_content = str(segment)
                                        color = None
                                        is_bold = False
                                        is_italic = False
                                    
                                    # If there's a color or styling, use tspan
                                    if color or is_bold or is_italic:
                                        tspan_style = ''
                                        if color:
                                            tspan_style += f' fill="{color}"'
                                        if is_bold:
                                            tspan_style += ' font-weight="bold"'
                                        if is_italic:
                                            tspan_style += ' font-style="italic"'
                                        
                                        svg_lines.append(f'        <tspan{tspan_style}>{html.escape(text_content)}</tspan>')
                                    else:
                                        # Default color and styling
                                        tspan_style = f' fill="{label.get("textColor", "#000000")}"'
                                        svg_lines.append(f'        <tspan{tspan_style}>{html.escape(text_content)}</tspan>')
                                
                                svg_lines.append('      </text>')
                else:
                    # Simple text label - use relative coordinates from GraphML
                    text_attrs = f'font-family="{font_family}" font-size="{font_size}" font-style="{font_style}" font-weight="{font_weight}" fill="{label.get("textColor", "#000000")}" text-anchor="{text_anchor}" dominant-baseline="middle" stroke="none"'
                    
                    # Position text using label coordinates (relative to shape geometry)
                    # Note: we're now inside a transform group, so coordinates are relative to the node
                    label_rel_x = label.get('x', 0)
                    label_rel_y = label.get('y', 0)
                    label_width = label.get('width', geom['width'])
                    label_height = label.get('height', geom['height'])
                    
                    # Calculate position (now relative to node, not absolute)
                    if label_rel_x == 0 and label_rel_y == 0:
                        # No explicit position: center in shape (default behavior)
                        label_x = geom['width'] / 2
                        label_y = geom['height'] / 2
                    else:
                        # Adjust for text-anchor alignment (same as in draw_node_labels)
                        # For SVG with text-anchor, we must position the text anchor point correctly
                        if text_anchor == 'start':
                            label_x = label_rel_x
                        elif text_anchor == 'end':
                            label_x = label_rel_x + label_width
                        else:  # middle (default)
                            label_x = label_rel_x + label_width / 2
                        
                        # For Y, use the center of the label box
                        label_y = label_rel_y + label_height / 2
                    
                    svg_lines.append('      <text x="{}" y="{}" {}>'.format(
                        label_x, label_y, text_attrs
                    ))
                    svg_lines.append(html.escape(str(label.get('text', ''))))
                    svg_lines.append('      </text>')
        
        # Close render group and transform group
        svg_lines.append('    </g>')
        svg_lines.append('    </g>')
    
    return svg_lines

def calculate_edge_intersection_point(
    source_geom: Dict[str, float],
    target_geom: Dict[str, float],
    path_sx: float = 0,
    path_sy: float = 0
) -> tuple:
    """
    Calculate where an edge line intersects the boundary of the source node.
    
    For yEd compatibility, this implements the automatic boundary detection
    that yEd does when rendering edges.
    
    Args:
        source_geom: Source node geometry {x, y, width, height}
        target_geom: Target node geometry {x, y, width, height}
        path_sx: X offset from source center
        path_sy: Y offset from source center
    
    Returns:
        (edge_start_x, edge_start_y) - point where edge meets source node boundary
    """
    # Source and target centers
    src_cx = source_geom['x'] + source_geom['width'] / 2
    src_cy = source_geom['y'] + source_geom['height'] / 2
    tgt_cx = target_geom['x'] + target_geom['width'] / 2
    tgt_cy = target_geom['y'] + target_geom['height'] / 2
    
    # Edge direction (from source to target, with offsets)
    start_x = src_cx + path_sx
    start_y = src_cy + path_sy
    
    dx = tgt_cx - start_x
    dy = tgt_cy - start_y
    
    # If direction is zero (source == target), return source center
    if dx == 0 and dy == 0:
        return (start_x, start_y)
    
    # Normalize direction
    length = (dx**2 + dy**2)**0.5
    dx_norm = dx / length
    dy_norm = dy / length
    
    # Source node bounds (relative to center)
    half_width = source_geom['width'] / 2
    half_height = source_geom['height'] / 2
    
    # Calculate distances to each boundary
    if dx_norm > 0:
        t_right = half_width / dx_norm
    elif dx_norm < 0:
        t_right = -half_width / dx_norm
    else:
        t_right = float('inf')
    
    if dy_norm > 0:
        t_bottom = half_height / dy_norm
    elif dy_norm < 0:
        t_bottom = -half_height / dy_norm
    else:
        t_bottom = float('inf')
    
    # The shortest distance is the intersection point
    t_intersection = min(t_right, t_bottom)
    
    # Calculate intersection point
    int_x = src_cx + t_intersection * dx_norm
    int_y = src_cy + t_intersection * dy_norm
    
    return (int_x, int_y)

def calculate_line_rectangle_intersection(start_pt, direction_x, direction_y, rect_cx, rect_cy, rect_w, rect_h):
    """
    Calculate where a ray from start_pt in direction (direction_x, direction_y)
    intersects the rectangle boundary.
    
    Args:
        start_pt: dict with 'x' and 'y' - starting point of the ray
        direction_x, direction_y: direction vector (will be normalized)
        rect_cx, rect_cy: center of rectangle
        rect_w, rect_h: width and height of rectangle
    
    Returns:
        (x, y) intersection point on rectangle boundary, or None if no intersection
    """
    # Normalize direction
    dist = math.sqrt(direction_x**2 + direction_y**2)
    if dist < 1e-10:
        return None
    
    dx_norm = direction_x / dist
    dy_norm = direction_y / dist
    
    half_w = rect_w / 2
    half_h = rect_h / 2
    
    # Calculate intersection t for each of the 4 boundaries
    # We want the SMALLEST positive t (closest intersection)
    candidates = []
    
    # Right boundary: x = rect_cx + half_w
    if abs(dx_norm) > 1e-10:
        t = (rect_cx + half_w - start_pt['x']) / dx_norm
        if t > 1e-10:  # Must be positive (forward direction)
            # Check if intersection point is within rectangle height
            y_at_t = start_pt['y'] + t * dy_norm
            if abs(y_at_t - rect_cy) <= half_h + 1e-6:
                candidates.append((t, rect_cx + half_w, y_at_t))
    
    # Left boundary: x = rect_cx - half_w
    if abs(dx_norm) > 1e-10:
        t = (rect_cx - half_w - start_pt['x']) / dx_norm
        if t > 1e-10:
            y_at_t = start_pt['y'] + t * dy_norm
            if abs(y_at_t - rect_cy) <= half_h + 1e-6:
                candidates.append((t, rect_cx - half_w, y_at_t))
    
    # Bottom boundary: y = rect_cy + half_h
    if abs(dy_norm) > 1e-10:
        t = (rect_cy + half_h - start_pt['y']) / dy_norm
        if t > 1e-10:
            x_at_t = start_pt['x'] + t * dx_norm
            if abs(x_at_t - rect_cx) <= half_w + 1e-6:
                candidates.append((t, x_at_t, rect_cy + half_h))
    
    # Top boundary: y = rect_cy - half_h
    if abs(dy_norm) > 1e-10:
        t = (rect_cy - half_h - start_pt['y']) / dy_norm
        if t > 1e-10:
            x_at_t = start_pt['x'] + t * dx_norm
            if abs(x_at_t - rect_cx) <= half_w + 1e-6:
                candidates.append((t, x_at_t, rect_cy - half_h))
    
    # Return intersection point with smallest t (closest)
    if candidates:
        # Sort by t and take the first (smallest)
        candidates.sort(key=lambda x: x[0])
        t_min, x, y = candidates[0]
        return (x, y)
    
    return None

def draw_edges(edges: List[Dict[str, Any]], node_map: Dict[str, Dict[str, float]], 
               node_svg_bounds: Dict[str, Dict[str, float]]) -> List[str]:
    """
    Draw edges (connections between nodes) with arrows.
    
    Args:
        edges: List of edge dictionaries
        node_map: Mapping of node IDs to their geometry
        node_svg_bounds: Mapping of node IDs to their SVG bounds
    
    Returns:
        List of SVG line strings for edges
    """
    svg_lines = []
    
    for edge in edges:
        source_id = edge['source']
        target_id = edge['target']
        
        if source_id not in node_map or target_id not in node_map:
            continue
            
        source_geom = node_map[source_id]
        target_geom = node_map[target_id]
        
        # Centers in world coordinates
        source_cx = source_geom['x'] + source_geom['width'] / 2
        source_cy = source_geom['y'] + source_geom['height'] / 2
        target_cx = target_geom['x'] + target_geom['width'] / 2
        target_cy = target_geom['y'] + target_geom['height'] / 2
        
        # Check if edge has specific path offsets (sx, sy, tx, ty)
        # These are relative offsets from the center of the source and target nodes
        path_sx = edge.get('path_sx', 0)
        path_sy = edge.get('path_sy', 0)
        path_tx = edge.get('path_tx', 0)
        path_ty = edge.get('path_ty', 0)
        
        # Calculate actual start and end points with offsets
        if path_sx != 0 or path_sy != 0 or path_tx != 0 or path_ty != 0:
            # Use the offsets to get the actual connection points on the node boundaries
            start_x = source_cx + path_sx
            start_y = source_cy + path_sy
            end_x = target_cx + path_tx
            end_y = target_cy + path_ty
        else:
            # Fallback: calculate from centers (legacy behavior)
            start_x = source_cx
            start_y = source_cy
            end_x = target_cx
            end_y = target_cy
        
        # Get bounds (SVG or geometry)
        source_bounds = source_geom
        if source_id in node_svg_bounds:
            sb = node_svg_bounds[source_id]
            source_bounds = {
                'x': source_geom['x'] + sb['x'],
                'y': source_geom['y'] + sb['y'],
                'width': sb['width'],
                'height': sb['height']
            }
        
        target_bounds = target_geom
        if target_id in node_svg_bounds:
            tb = node_svg_bounds[target_id]
            target_bounds = {
                'x': target_geom['x'] + tb['x'],
                'y': target_geom['y'] + tb['y'],
                'width': tb['width'],
                'height': tb['height']
            }
        
        # Build the path segments
        path_points = edge.get('path_points', [])
        
        # Calculate arrow endpoint points (P_arrow_0 for source, P_arrow_1 for target)
        p_arrow_0 = None
        p_arrow_1 = None
        
        if path_points:
            # Path: start_point → point1 → ... → pointN → end_point
            # Points already include path offsets if they exist
            points = [{'x': start_x, 'y': start_y}]
            for pt in path_points:
                points.append({'x': pt['x'], 'y': pt['y']})
            points.append({'x': end_x, 'y': end_y})
        else:
            # Direct line: use the calculated start/end points (may have offsets)
            # The start and end points were already calculated with offsets above
            points = [
                {'x': start_x, 'y': start_y},
                {'x': end_x, 'y': end_y}
            ]
        
        # Store edge start and end positions for label positioning
        edge['_start_y'] = points[0]['y']
        edge['_end_y'] = points[-1]['y']
        
        line_color = edge.get('line_color', '#000000')
        line_width = edge.get('line_width', 1.0)
        line_type = edge.get('line_type', 'line')
        arrow_target = edge.get('arrow_target', 'none')
        arrow_source = edge.get('arrow_source', 'none')
        smoothed = edge.get('smoothed', False)
        
        # Get line style attributes
        line_styles = get_line_style_attributes(line_type, line_width)
        
        # Build stroke attributes string
        stroke_attrs = f'stroke="{line_color}" stroke-width="{line_width}"'
        for key, value in line_styles.items():
            stroke_attrs += f' {key}="{value}"'
        
        # ==============================================================================
        # CALCULATE P_ARROW_0 (intersection with source node rectangle)
        # ==============================================================================
        p_arrow_0 = None
        angle_arrow_0 = 0
        
        if arrow_source != 'none' and len(points) >= 2:
            # Direction: from the start point toward the next point
            start_pt = points[0]
            next_pt = points[1]
            dx = next_pt['x'] - start_pt['x']
            dy = next_pt['y'] - start_pt['y']
            
            # Use the robust intersection function
            intersection = calculate_line_rectangle_intersection(
                start_pt, dx, dy,
                source_cx, source_cy,
                source_geom['width'], source_geom['height']
            )
            
            if intersection:
                p_arrow_0 = intersection
                angle_arrow_0 = math.atan2(dy, dx) * 180 / math.pi
        
        # ==============================================================================
        # CALCULATE P_ARROW_1 (intersection with target node rectangle)
        # ==============================================================================
        p_arrow_1 = None
        angle_arrow_1 = 0
        
        if arrow_target != 'none' and len(points) >= 2:
            # Direction: from the previous point toward the last point
            prev_pt = points[-2]
            end_pt = points[-1]
            dx = end_pt['x'] - prev_pt['x']
            dy = end_pt['y'] - prev_pt['y']
            
            # Use the robust intersection function
            intersection = calculate_line_rectangle_intersection(
                prev_pt, dx, dy,
                target_cx, target_cy,
                target_geom['width'], target_geom['height']
            )
            
            if intersection:
                p_arrow_1 = intersection
                angle_arrow_1 = math.atan2(dy, dx) * 180 / math.pi
        
        # ==============================================================================
        # SHORTEN THE EDGE TO STOP AT ARROW ENDPOINTS
        # ==============================================================================
        display_points = [pt.copy() for pt in points]
        
        # Shorten at source end
        if p_arrow_0 is not None and len(points) >= 2:
            display_points[0] = {'x': p_arrow_0[0], 'y': p_arrow_0[1]}
        
        # Shorten at target end
        if p_arrow_1 is not None and len(points) >= 2:
            display_points[-1] = {'x': p_arrow_1[0], 'y': p_arrow_1[1]}
        
        svg_lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision">')
        
        # Draw edge (using shortened display_points)
        if smoothed and len(display_points) > 2:
            # Smoothed path with rounded corners
            path_d = build_rounded_path(display_points, radius=5)
            svg_lines.append(f'      <path fill="none" d="{path_d}" {stroke_attrs}/>')
        elif len(display_points) > 2:
            # Regular path without smoothing
            path_d = f"M {display_points[0]['x']},{display_points[0]['y']}"
            for i in range(1, len(display_points)):
                path_d += f" L {display_points[i]['x']},{display_points[i]['y']}"
            svg_lines.append(f'      <path fill="none" d="{path_d}" {stroke_attrs}/>')
        else:
            # Simple line
            svg_lines.append(f'      <line x1="{display_points[0]['x']}" y1="{display_points[0]['y']}" x2="{display_points[-1]['x']}" y2="{display_points[-1]['y']}" {stroke_attrs}/>')
        
        # ==============================================================================
        # DRAW ARROWS AT THE ENDPOINTS
        # ==============================================================================
        
        # Draw arrow at source endpoint (start of edge)
        if p_arrow_0 is not None and arrow_source != 'none':
            arrow_path = create_arrow_path(p_arrow_0[0], p_arrow_0[1], angle_arrow_0, arrow_source, line_color, line_width)
            svg_lines.append('      ' + arrow_path)
        
        # Draw arrow at target endpoint (end of edge)
        if p_arrow_1 is not None and arrow_target != 'none':
            arrow_path = create_arrow_path(p_arrow_1[0], p_arrow_1[1], angle_arrow_1, arrow_target, line_color, line_width)
            svg_lines.append('      ' + arrow_path)
        
        svg_lines.append('    </g>')
    
    return svg_lines

def draw_edge_label_background(x: float, y: float, width: float, height: float) -> List[str]:
    """Render le background blanc du label (rectangle rempli)."""
    # x et y sont déjà les coordonnées TOP-LEFT (pas le centre)
    rect_x = x
    rect_y = y
    lines = []
    lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision" fill="white" stroke="white" stroke-width="1.0" stroke-miterlimit="1.45">')
    lines.append('      <rect x="{}" y="{}" width="{}" height="{}" stroke="none"/>'.format(
        rect_x, rect_y, width, height
    ))
    lines.append('    </g>')
    return lines

def draw_edge_label_text(label: Dict[str, Any], x: float, y: float, width: float, height: float) -> List[str]:
    """Render le texte et le border du label."""
    lines = []
    
    # x et y sont déjà les coordonnées TOP-LEFT (pas le centre)
    rect_x = x
    rect_y = y
    line_color = label.get('lineColor', '#000000')
    
    # Map font attributes
    font_family = map_font_family(label['fontFamily'])
    font_style, font_weight = get_font_style_attributes(label['fontStyle'])
    text_anchor_override = 'start'
    
    # Border rectangle
    lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision" fill="{}" stroke="{}" stroke-width="1.0" stroke-miterlimit="1.45">'.format(
        line_color, line_color
    ))
    lines.append('      <rect x="{}" y="{}" width="{}" height="{}" fill="none"/>'.format(
        rect_x, rect_y, width, height
    ))
    
    # Text positioning
    text_center_y = rect_y + height / 2
    label_x_text = rect_x + 3  # Small padding from left edge
    label_y_text = text_center_y
    
    # Text attributes
    text_attrs = 'font-family="{}" stroke-linecap="butt" font-size="{}" font-style="{}" font-weight="{}" fill="{}" text-anchor="{}" dominant-baseline="middle" stroke="none" stroke-miterlimit="1.45"'.format(
        font_family,
        label['fontSize'],
        font_style,
        font_weight,
        label['textColor'],
        text_anchor_override
    )
    
    # Handle multi-line labels
    label_text = label['text']
    if isinstance(label_text, list):
        label_text = '\n'.join(str(item) for item in label_text)
    elif not isinstance(label_text, str):
        label_text = str(label_text) if label_text else ''
    # escape entire text now (safe even if it contains newlines)
    label_text = html.escape(label_text)
    text_lines = label_text.split('\n')
    
    if len(text_lines) == 1:
        # Single line
        lines.append('      <text x="{}" y="{}" {} xml:space="preserve">{}</text>'.format(
            label_x_text,
            label_y_text,
            text_attrs,
            html.escape(label_text)
        ))
    else:
        # Multi-line with tspan
        font_size_num = label['fontSize']
        line_height = font_size_num + 2
        start_y = rect_y + line_height / 2
        
        lines.append('      <text x="{}" y="{}" {} xml:space="preserve">'.format(
            label_x_text,
            start_y,
            text_attrs
        ))
        
        for line_idx, line in enumerate(text_lines):
            if line_idx == 0:
                lines.append(html.escape(line))
            else:
                lines.append('        <tspan x="{}" dy="{}">{}</tspan>'.format(
                    label_x_text,
                    line_height,
                    html.escape(line)
                ))
        
        lines.append('      </text>')
    
    lines.append('    </g>')
    return lines

def draw_edges_labels(edges: List[Dict[str, Any]], node_map: Dict[str, Dict[str, float]], bg_x: float, bg_y: float, groups: List[Dict[str, Any]] = None, graphml_data: Dict[str, Any] = None) -> List[str]:
    """
    Draw text labels for edges (OUTSIDE the main transform group).
    Handles edges with multiple labels by rendering each label separately.
    
    Uses SmartEdgeLabel "safe zone" positioning with ratio/distance-based placement.
    Implements the complete algorithm from graphml2jpg.py for accurate label positioning.
    
    Cas spécial: Si le node label du source se trouve sur le segment 0 (vertical ou horizontal),
    le point de départ de la safe zone devient le centre du node label.
    
    Args:
        edges: List of edge dictionaries with label information
        node_map: Mapping of node IDs to their geometry
        bg_x, bg_y: Background offset for coordinate transformation
        groups: Optional list of group dictionaries for coordinate conversion
        graphml_data: Optional graphml data dict containing node information (for node labels)
    
    Returns:
        List of SVG line strings for edge labels
    """
    svg_lines = []
    
    if groups is None:
        groups = []
    
    if graphml_data is None:
        graphml_data = {'nodes': []}
    
    for edge in edges:
        # Récupérer les labels à renderer
        labels_to_render = edge.get('labels', [])
        if not labels_to_render and 'label' in edge:
            labels_to_render = [edge['label']]
        
        source_id = edge.get('source')
        target_id = edge.get('target')
        
        # Skip si nœuds invalides
        if source_id not in node_map or target_id not in node_map:
            continue
        
        source_geom = node_map[source_id]
        target_geom = node_map[target_id]
        source_center = (source_geom['x'] + source_geom['width'] / 2,
                        source_geom['y'] + source_geom['height'] / 2)
        target_center = (target_geom['x'] + target_geom['width'] / 2,
                        target_geom['y'] + target_geom['height'] / 2)
        
        # Calculer le centre du node label du source (pour détecter les chevauchements avec le segment 0)
        source_node_label_center = None
        source_node = next((n for n in graphml_data.get('nodes', []) if n.get('id') == source_id), None)
        if source_node and 'label' in source_node:
            label = source_node['label']
            label_abs_x = source_geom['x'] + label.get('x', 0.0)
            label_abs_y = source_geom['y'] + label.get('y', 0.0)
            label_width = label.get('width', 0.0)
            label_height = label.get('height', 0.0)
            source_node_label_center = (
                label_abs_x + label_width / 2,
                label_abs_y + label_height / 2
            )
        
        # Récupérer les données du chemin
        path_points = edge.get('path_points', [])
        path_sx = edge.get('path_sx', 0.0)
        path_sy = edge.get('path_sy', 0.0)
        path_tx = edge.get('path_tx', 0.0)
        path_ty = edge.get('path_ty', 0.0)
        default_distance = edge.get('default_distance', 10.0)
        
        for label_idx, label in enumerate(labels_to_render):
            if not label.get('text'):
                continue
            
            # Récupérer les paramètres du label
            label_width = label.get('width', 0.0)
            label_height = label.get('height', 0.0)
            
            # Vérifier si le label a SmartEdgeLabelModelParameter
            has_smart_params = 'smart_edge_label_model_parameter' in label
            
            if has_smart_params:
                # Utiliser la logique de safe zone complète
                smart_params = label['smart_edge_label_model_parameter']
                segment_index = int(smart_params.get('segment', 0))
                ratio = float(smart_params.get('ratio', 0.5))
                
                try:
                    # Calculer la position sur le segment avec la safe zone
                    # Cette fonction retourne le CENTRE du label
                    label_center_x, label_center_y = calculate_label_position_on_segment(
                        segment_index, ratio, default_distance,
                        source_center, target_center, path_points,
                        path_sx, path_sy, path_tx, path_ty,
                        source_node_label_center
                    )
                    # Convertir du centre au coin supérieur gauche
                    x_monde = label_center_x - label_width / 2
                    y_monde = label_center_y - label_height / 2
                except Exception as e:
                    # Fallback: utiliser les offsets XML simples
                    label_rel_x = label.get('x', 0.0)
                    label_rel_y = label.get('y', 0.0)
                    x_monde = source_center[0] + label_rel_x
                    y_monde = source_center[1] + label_rel_y
            else:
                # Sans SmartEdgeLabelModelParameter: utiliser directement les offsets XML
                # (relativement au centre du nœud source, mais les offsets XML sont déjà
                # relatifs à la position TOP-LEFT, pas au centre)
                label_rel_x = label.get('x', 0.0)
                label_rel_y = label.get('y', 0.0)
                x_monde = source_center[0] + label_rel_x
                y_monde = source_center[1] + label_rel_y
            
            # Renderer le background et le texte
            # x_monde et y_monde sont maintenant les coordonnées du COIN SUPERIEUR GAUCHE
            rect_width = label.get('width', 0.0)
            rect_height = label.get('height', 0.0)
            
            # Background blanc
            svg_lines.extend(draw_edge_label_background(x_monde, y_monde, rect_width, rect_height))
            
            # Texte et border
            svg_lines.extend(draw_edge_label_text(label, x_monde, y_monde, rect_width, rect_height))
    
    return svg_lines

def draw_nodes(nodes: List[Dict[str, Any]], node_clip_paths: Dict[str, str] = None) -> List[str]:
    """
    Draw regular nodes with embedded SVG content.
    
    Args:
        nodes: List of node dictionaries
        node_clip_paths: Dictionary mapping node IDs to their individual clipPath IDs
    
    Returns:
        List of SVG line strings for nodes
    """
    svg_lines = []
    
    if node_clip_paths is None:
        node_clip_paths = {}
    
    for node in nodes:
        if 'geometry' not in node or 'svg_content' not in node:
            continue
        
        geom = node['geometry']
        svg_content = node['svg_content']
        node_id = node.get('id', '')
        
        # Clean embedded SVG content (remove XML declaration and comments)
        svg_content = clean_embedded_svg(svg_content)
        
        # Fix SVG dimensions to match the node geometry exactly
        # Replace width and height attributes ONLY in the root SVG tag, not nested SVG elements
        svg_width = str(geom['width'])
        svg_height = str(geom['height'])
        
        # Replace width and height only in the opening root <svg> tag
        # This regex matches <svg ... width="..." ... /> or <svg ... width="..." ... >
        svg_content = re.sub(
            r'(<svg\s[^>]*?)width="[^"]*"',
            rf'\1width="{svg_width}"',
            svg_content,
            count=1
        )
        svg_content = re.sub(
            r'(<svg\s[^>]*?)height="[^"]*"',
            rf'\1height="{svg_height}"',
            svg_content,
            count=1
        )
        
        # Transform node position (world coordinates)
        translate_x = geom['x']
        translate_y = geom['y']
        
        # Get the clipPath for this node (MUST be in the dictionary)
        # If not found, it means the clipPath wasn't created during build_svg_structure
        if node_id not in node_clip_paths:
            # Create a fallback clipPath for this node on-the-fly
            # This ensures ALL SVG nodes get properly clipped regardless
            fallback_clip_id = f'clipPath_fallback_{node_id}'
            node_clip_paths[node_id] = fallback_clip_id
            clip_path_id = fallback_clip_id
        else:
            clip_path_id = node_clip_paths[node_id]
        
        svg_lines.append('    <g text-rendering="geometricPrecision" shape-rendering="geometricPrecision" transform="matrix(1,0,0,1,{},{})">'.format(translate_x, translate_y))
        svg_lines.append('      <g clip-path="url(#{})">'.format(clip_path_id))
        
        # Wrap embedded SVG content in a container group to isolate any structural issues
        # This prevents unbalanced <g> tags from breaking the overall SVG structure
        svg_lines.append('        <g>')
        
        # Insert embedded SVG content
        svg_lines.append(svg_content)
        
        # Close the content wrapper group
        svg_lines.append('        </g>')
        
        svg_lines.append('      </g>')
        svg_lines.append('    </g>')
    
    return svg_lines

def draw_node_labels(nodes: List[Dict[str, Any]], bg_x: float, bg_y: float) -> List[str]:
    """
    Draw text labels for nodes positioned below them.
    Supports both plain text and HTML labels.
    Handles line breaks in labels.
    Supports multiple labels per node (SVGNode with multiple NodeLabels).
    
    Args:
        nodes: List of node dictionaries
        bg_x, bg_y: Background offset coordinates (unused, kept for API consistency)
    
    Returns:
        List of SVG line strings for node labels
    """
    svg_lines = []
    
    for node in nodes:
        if 'geometry' not in node:
            continue
        
        geom = node['geometry']
        
        # Check if node has multiple labels or single label
        labels_to_draw = []
        if 'labels' in node:
            # SVGNode with multiple labels
            labels_to_draw = node['labels']
        elif 'label' in node:
            # Single label (backward compatibility or ShapeNode)
            labels_to_draw = [node['label']]
        
        if not labels_to_draw:
            continue
        
        # Wrap all labels for this node in a group with the node's transform
        # This compensates for the parent group's transform that shifts everything by (-bg_x, -bg_y)
        node_x = geom['x']
        node_y = geom['y']
        svg_lines.append('    <g transform="matrix(1,0,0,1,{},{})">'.format(node_x, node_y))
        
        # Draw each label
        for label in labels_to_draw:
            label_text = label.get('text', '')
            if not label_text:
                continue
            
            # Map font family
            font_family = map_font_family(label.get('fontFamily', 'Dialog'))
            
            # Determine text anchor based on alignment
            alignment = label.get('alignment', 'center')
            if alignment == 'left':
                text_anchor = 'start'
            elif alignment == 'right':
                text_anchor = 'end'
            else:
                text_anchor = 'middle'
            
            # Determine positioning based on modelName
            model_name = label.get('modelName', 'internal')
            model_position = label.get('modelPosition', 'c')
            
            if model_name == 'sandwich' and model_position == 's':
                # Old-style "sandwich" labels positioned below node (backward compatibility)
                # Center horizontally on the node (relative coordinates since we're in node's group)
                label_x = geom['width'] / 2
                # Position vertically below the node
                label_y = geom['height'] + label.get('fontSize', 12) + 4
            else:
                # Custom positioned labels using GraphML coordinates
                # Get label position from attributes (relative to node's top-left corner)
                label_local_x = label.get('x', 0)
                label_local_y = label.get('y', 0)
                label_local_width = label.get('width', geom['width'])
                label_local_height = label.get('height', geom['height'])
                
                # Convert to local coordinates (relative to node, since we're in the node's transform group)
                # NOTE: For SVG with text-anchor, the label position should be where the text ANCHOR is placed
                # yEd's label coordinates are relative to node's top-left, so we use them directly
                # But we must adjust for text-anchor alignment:
                # - text-anchor="start" (left align): place at label_x
                # - text-anchor="middle" (center align): place at label_x + label_width/2  
                # - text-anchor="end" (right align): place at label_x + label_width
                
                # For y-axis: SVG uses dominant-baseline which affects vertical positioning
                # GraphML label y is the top of the label box, SVG typically uses baseline
                # We adjust by using label_y + label_height/2 to approximate centering
                
                if text_anchor == 'start':
                    label_x = label_local_x
                elif text_anchor == 'end':
                    label_x = label_local_x + label_local_width
                else:  # middle (default)
                    label_x = label_local_x + label_local_width / 2
                
                # For Y, use the center of the label box for better vertical alignment
                label_y = label_local_y + label_local_height / 2
            
            # Determine stroke attribute
            has_line_color = label.get('hasLineColor', False)
            stroke_attr = 'stroke="{}"{}'.format(
                label.get('textColor', '#000000'),
                ''
            ) if has_line_color else 'stroke="none"'
            
            # Check if label contains HTML
            if label_text.startswith('<'):
                # Parse HTML content
                html_data = parse_html_label(label_text)
                
                # Check if it's a table
                if html_data.get('is_table', False):
                    # Draw HTML table as SVG
                    padding = 6
                    table_x = label_x - geom['width'] / 2 + padding
                    table_y = label_y - label.get('fontSize', 12)
                    table_width = geom['width'] - 2 * padding
                    table_height = geom['height'] - 2 * padding
                    
                    table_svg = draw_html_table_as_svg(
                        html_data['rows'],
                        table_x, table_y,
                        table_width, table_height,
                        font_size=label.get('fontSize', 12),
                        text_color=label.get('textColor', '#000000')
                    )
                    svg_lines.extend(table_svg)
                else:
                    # Draw as text lines
                    text_lines = html_data.get('lines', [])
                    if text_lines:
                        svg_lines.append('    <g text-rendering="geometricPrecision" stroke-miterlimit="10" shape-rendering="geometricPrecision" font-family="{}">'.format(font_family))
                        line_height = label.get('fontSize', 12) * 1.2
                        for i, line in enumerate(text_lines):
                            # Handle case where line is a list of segments or a string
                            if isinstance(line, list):
                                # line is a list of segment dicts
                                line_text = ''.join(segment.get('text', '') for segment in line)
                            else:
                                line_text = str(line) if line else ''
                            
                            line_y = label_y + i * line_height
                            svg_lines.append('      <text x="{}" xml:space="preserve" y="{}" text-anchor="{}" {}>{}</text>'.format(
                                label_x,
                                line_y,
                                text_anchor,
                                stroke_attr,
                                line_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                            ))
                        svg_lines.append('    </g>')
            else:
                # Plain text label - handle line breaks
                text_lines = label_text.split('\n')
                svg_lines.append('    <g text-rendering="geometricPrecision" stroke-miterlimit="10" shape-rendering="geometricPrecision" font-family="{}">'.format(font_family))
                line_height = label.get('fontSize', 12) * 1.2
                for i, line in enumerate(text_lines):
                    line_y = label_y + i * line_height
                    svg_lines.append('      <text x="{}" xml:space="preserve" y="{}" text-anchor="{}" {}>{}</text>'.format(
                        label_x, 
                        line_y,
                        text_anchor,
                        stroke_attr,
                        line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    ))
                svg_lines.append('    </g>')
        
        # Close the node's transform group
        svg_lines.append('    </g>')
    
    return svg_lines

# ═════════════════════════════════════════════════════════════════════════════
# BOUNDS CALCULATION - Include edges and labels
# ═════════════════════════════════════════════════════════════════════════════

def build_svg_structure(graphml_data: Dict[str, Any]) -> str:
    """
    Build SVG structure from parsed GraphML data.
    
    Includes:
    - Proper SVG bounds and dimensions
    - Clip paths and clipping regions (clipPath3)
    - Basic CSS styles for nodes, edges, and labels
    - Background rectangles
    - Group nodes (drawn first as background elements)
    - Shape nodes (rectangles, circles, diamonds, etc.)
    - Edges (connections between nodes with arrows)
    - Regular nodes with embedded SVG content (custom shapes)
    - Text labels for nodes
    - Text labels for edges
    - Proper coordinate transformations (world-to-SVG)
    
    SVG Structure:
    ├── <svg> - Main SVG container
    │   ├── <defs> - Definitions for reusable elements
    │   │   ├── <clipPath id="clipPath3"> - Clipping region
    │   │   └── <style> - CSS styles
    │   └── <g> - Main group
    │       ├── Background (white rectangle)
    │       └── <g transform="matrix(...)"> - World coordinates
    │           ├── Group nodes
    │           ├── Shape nodes
    │           ├── Edges
    │           ├── Nodes with embedded SVG
    │           ├── Node labels
    │           └── Edge labels
    
    Note: Embedded SVG content is cleaned by clean_embedded_svg() which removes:
    - XML declarations (<?xml ...?>)
    - HTML comments (<!-- ... -->)
    - Unnecessary whitespace
    
    The clipPath3 reference ensures all content is clipped to the SVG viewport.
    """
    nodes = graphml_data['nodes']
    shape_nodes = graphml_data.get('shape_nodes', [])
    groups = graphml_data.get('groups', [])
    edges = graphml_data['edges']
    
    # Margin around the SVG
    MARGIN = 15
    
    # Create a mapping of node IDs to their geometry
    node_map = {}
    node_svg_bounds = {}
    
    # Include regular nodes (SVGNode type)
    for node in nodes:
        if 'geometry' in node:
            node_map[node['id']] = node['geometry']
            if 'svg_bounds' in node:
                node_svg_bounds[node['id']] = node['svg_bounds']
    
    # BUGFIX: Also include shape_nodes (ShapeNode type) in node_map
    # This ensures that nodes from groups (which are ShapeNodes) can be referenced by edges
    for shape_node in shape_nodes:
        if 'geometry' in shape_node:
            node_map[shape_node['id']] = shape_node['geometry']
            if 'svg_bounds' in shape_node:
                node_svg_bounds[shape_node['id']] = shape_node['svg_bounds']
    
    # Create a mapping of group IDs to their geometry
    group_map = {}
    for group in groups:
        if 'geometry' in group:
            group_map[group['id']] = group
    
    # Calculate bounds from all nodes, groups, shape_nodes, edge path points
    # BUGFIX: Only include nodes that are NOT inside groups, since groups already include their children
    grouped_node_ids = set()
    for group in groups:
        group_id = group.get('id', '')
        for node in nodes:
            node_id = node.get('id', '')
            if node_id.startswith(group_id + '::'):
                grouped_node_ids.add(node_id)
    
    # Only include nodes that are not grouped
    all_geometries = [n['geometry'] for n in nodes if 'geometry' in n and n['id'] not in grouped_node_ids]
    all_geometries += [g['geometry'] for g in groups if 'geometry' in g]
    all_geometries += [s['geometry'] for s in shape_nodes if 'geometry' in s]
    
    # BUGFIX: Include edge path points and edge labels in bounds calculation
    # This ensures the SVG is large enough to display all content
    edge_x_coords, edge_y_coords = calculate_edges_labels_bounds(edges, node_map, nodes, groups)
    
    # Calculate bounds from edge labels including their dimensions
    edge_label_bounds = []
    for edge in edges:
        labels_to_render = edge.get('labels', [])
        if not labels_to_render and 'label' in edge:
            labels_to_render = [edge['label']]
        
        source_id = edge.get('source')
        target_id = edge.get('target')
        
        if source_id not in node_map or target_id not in node_map:
            continue
        
        source_geom = node_map[source_id]
        target_geom = node_map[target_id]
        source_center = (source_geom['x'] + source_geom['width'] / 2,
                        source_geom['y'] + source_geom['height'] / 2)
        target_center = (target_geom['x'] + target_geom['width'] / 2,
                        target_geom['y'] + target_geom['height'] / 2)
        
        path_points = edge.get('path_points', [])
        path_sx = edge.get('path_sx', 0.0)
        path_sy = edge.get('path_sy', 0.0)
        path_tx = edge.get('path_tx', 0.0)
        path_ty = edge.get('path_ty', 0.0)
        default_distance = edge.get('default_distance', 10.0)
        
        # Calculer le centre du node label du source
        source_node_label_center = None
        source_node = next((n for n in graphml_data.get('nodes', []) if n.get('id') == source_id), None)
        if source_node and 'label' in source_node:
            label = source_node['label']
            label_abs_x = source_geom['x'] + label.get('x', 0.0)
            label_abs_y = source_geom['y'] + label.get('y', 0.0)
            label_width = label.get('width', 0.0)
            label_height = label.get('height', 0.0)
            source_node_label_center = (
                label_abs_x + label_width / 2,
                label_abs_y + label_height / 2
            )
        
        for label in labels_to_render:
            if not label.get('text'):
                continue
            
            label_width = label.get('width', 0.0)
            label_height = label.get('height', 0.0)
            has_smart_params = 'smart_edge_label_model_parameter' in label
            
            if has_smart_params:
                smart_params = label['smart_edge_label_model_parameter']
                segment_index = int(smart_params.get('segment', 0))
                ratio = float(smart_params.get('ratio', 0.5))
                
                try:
                    label_center_x, label_center_y = calculate_label_position_on_segment(
                        segment_index, ratio, default_distance,
                        source_center, target_center, path_points,
                        path_sx, path_sy, path_tx, path_ty,
                        source_node_label_center
                    )
                    # Convertir du centre au coin supérieur gauche
                    x_monde = label_center_x - label_width / 2
                    y_monde = label_center_y - label_height / 2
                except:
                    # Fallback
                    label_rel_x = label.get('x', 0.0)
                    label_rel_y = label.get('y', 0.0)
                    x_monde = source_center[0] + label_rel_x
                    y_monde = source_center[1] + label_rel_y
            else:
                label_rel_x = label.get('x', 0.0)
                label_rel_y = label.get('y', 0.0)
                x_monde = source_center[0] + label_rel_x
                y_monde = source_center[1] + label_rel_y
            
            # Ajouter les bounds du label (coin sup-gauche + dimensions)
            edge_label_bounds.append(x_monde)
            edge_label_bounds.append(y_monde)
            edge_label_bounds.append(x_monde + label_width)
            edge_label_bounds.append(y_monde + label_height)
    
    if not all_geometries:
        if edge_x_coords and edge_y_coords:
            # Use edge bounds if no nodes
            min_x = min(edge_x_coords)
            min_y = min(edge_y_coords)
            max_x = max(edge_x_coords)
            max_y = max(edge_y_coords)
        else:
            min_x = min_y = 0
            max_x = 78
            max_y = 119
    else:
        # Calculate bounds from nodes
        min_x = min(g['x'] for g in all_geometries)
        min_y = min(g['y'] for g in all_geometries)
        max_x = max(g['x'] + g['width'] for g in all_geometries)
        max_y = max(g['y'] + g['height'] for g in all_geometries)
        
        # Expand bounds to include edges and labels if they extend beyond
        if edge_x_coords and edge_y_coords:
            min_x = min(min_x, min(edge_x_coords))
            min_y = min(min_y, min(edge_y_coords))
            max_x = max(max_x, max(edge_x_coords))
            max_y = max(max_y, max(edge_y_coords))
        
        # Expand bounds to include edge labels with their dimensions
        if edge_label_bounds:
            min_x = min(min_x, min(edge_label_bounds[i] for i in range(0, len(edge_label_bounds), 4)))
            min_y = min(min_y, min(edge_label_bounds[i] for i in range(1, len(edge_label_bounds), 4)))
            max_x = max(max_x, max(edge_label_bounds[i] for i in range(2, len(edge_label_bounds), 4)))
            max_y = max(max_y, max(edge_label_bounds[i] for i in range(3, len(edge_label_bounds), 4)))
    
    # Calculate SVG dimensions with margin using precise floating point values
    content_width = max_x - min_x
    content_height = max_y - min_y
    
    # Background position (with margin applied to world coordinates)
    # Use floor to ensure we always have at least the requested margin
    bg_x = min_x - MARGIN
    bg_y = min_y - MARGIN
    bg_x_int = int(math.floor(bg_x))
    bg_y_int = int(math.floor(bg_y))
    
    # Calculate SVG dimensions
    # We need the SVG to go from bg_x_int to at least max_x + MARGIN
    # width = (max_x + MARGIN) - bg_x_int, but we need to account for floating point precision
    width = int(math.ceil(max_x - bg_x_int + MARGIN))
    height = int(math.ceil(max_y - bg_y_int + MARGIN))
    
    # Start building SVG
    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" fill-opacity="1" color-rendering="auto" color-interpolation="auto" text-rendering="auto" stroke="black" stroke-linecap="square" width="{}" stroke-miterlimit="10" shape-rendering="auto" stroke-opacity="1" fill="black" stroke-dasharray="none" font-weight="normal" stroke-width="1" height="{}" font-family="\'Dialog\'" font-style="normal" stroke-linejoin="miter" font-size="12px" stroke-dashoffset="0" image-rendering="auto">'.format(width, height),
        '  <defs id="genericDefs">',
        '    <clipPath id="clipPath3">',
        '      <rect x="{}" y="{}" width="{}" height="{}"/>'.format(bg_x_int, bg_y_int, width, height),
        '    </clipPath>',
    ]
    
    # Create individual clipPath for each SVG node
    node_clip_paths = {}
    clip_path_counter = 4  # Start from 4 since 3 is used for global
    
    for node in nodes:
        if 'geometry' in node and 'svg_content' in node:
            node_id = node.get('id', '')
            geom = node['geometry']
            
            # Create a clipPath for this node sized to its geometry (NOT the SVG dimensions)
            # The clipPath should match the node's geometric dimensions to ensure proper clipping
            clip_path_id = f'clipPath{clip_path_counter}'
            node_clip_paths[node_id] = clip_path_id
            
            # Add clipPath definition: rect from (0,0) to (geometry_width, geometry_height) in local coordinates
            # This ensures the clipPath matches the node's actual size
            svg_lines.append('    <clipPath id="{}">'.format(clip_path_id))
            svg_lines.append('      <rect x="0" y="0" width="{}" height="{}"/>'.format(
                geom['width'], geom['height']))
            svg_lines.append('    </clipPath>')
            
            clip_path_counter += 1
    
    # Continue with styles
    svg_lines.extend([
        '    <style type="text/css">',
        '      <![CDATA[',
        '        .node { stroke: black; stroke-width: 1px; fill: white; }',
        '        .edge { stroke: black; stroke-width: 1px; fill: none; }',
        '        .label { font-family: Dialog, sans-serif; font-size: 12px; }',
        '      ]]>',
        '    </style>',
        '  </defs>',
        '  <g>'
    ])
    
    # Background rectangle with clipping
    svg_lines.append('    <g fill="white" text-rendering="geometricPrecision" shape-rendering="geometricPrecision" transform="translate({},{})">'.format(-bg_x_int, -bg_y_int))
    svg_lines.append('      <rect x="{}" width="{}" height="{}" y="{}" stroke="none"/>'.format(bg_x_int, width, height, bg_y_int))
    svg_lines.append('    </g>')
    
    # Main content group with world-to-SVG transform
    svg_lines.append('    <g transform="matrix(1,0,0,1,{},{})">'.format(-bg_x_int, -bg_y_int))
    
    # Draw group nodes (background elements, drawn before edges and nodes)
    svg_lines.extend(draw_group_nodes(groups, bg_x_int, bg_y_int))
    
    # Draw shape nodes
    svg_lines.extend(draw_shape_nodes(shape_nodes))
    
    # Draw edges (links between nodes) FIRST
    svg_lines.extend(draw_edges(edges, node_map, node_svg_bounds))
    
    # Draw nodes AFTER edges so they cover any transparent areas
    svg_lines.extend(draw_nodes(nodes, node_clip_paths))
    
    # Draw node labels before edge labels
    # BUGFIX: Include only regular nodes (not shape_nodes) because shape_nodes are already drawn with labels in draw_shape_nodes
    svg_lines.extend(draw_node_labels(nodes, bg_x_int, bg_y_int))
    
    # Draw edge labels INSIDE the transform group (so they get the same transformation as other elements)
    svg_lines.extend(draw_edges_labels(edges, node_map, bg_x_int, bg_y_int, groups, graphml_data))
    
    # Close main content group (transform group for world coordinates)
    svg_lines.append('    </g>')
    
    # Close main SVG group
    svg_lines.append('  </g>')
    
    # Close SVG
    svg_lines.append('</svg>')
    
    return '\n'.join(svg_lines)

def convert(input_path: str, output_path: str) -> str:
    """
    Convert GraphML file to SVG.
    
    Args:
        input_path: Path to the input .graphml file
        output_path: Path for the output .svg file
    
    Returns:
        The output file path on success
    
    Raises:
        FileNotFoundError: If input file doesn't exist
        Exception: If parsing or conversion fails
    """
    try:
        # Parse the GraphML file
        print(f"Parsing {input_path}...")
        graphml_data = parse_graphml(input_path)
        print(f"[OK] Parsed: {len(graphml_data['nodes'])} nodes, {len(graphml_data['edges'])} edges")
        
        # Build SVG structure
        print(f"Building SVG structure...")
        svg_content = build_svg_structure(graphml_data)
        print(f"[OK] SVG built: {len(svg_content)} chars")
        
        # Validate SVG content is not empty
        if not svg_content or len(svg_content.strip()) < 50:
            raise ValueError("Generated SVG content is empty or invalid")
        
        # Write to file with proper encoding
        print(f"Writing to {output_path}...")
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg_content)
        
        print(f"[OK] Successfully wrote {output_path}")
        return output_path
    
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Input file not found: {input_path}") from e
    except Exception as e:
        import traceback
        print(f"[ERROR] {str(e)}")
        traceback.print_exc()
        raise Exception(f"Error converting GraphML to SVG: {str(e)}") from e

if __name__ == '__main__':
    import sys
    import argparse
    import os

    DEBUG_MODE = False

    if DEBUG_MODE:
        result = convert("./graphml/simple3.graphml", "./target/simple3.svg")
        print(f"[OK] Successfully converted to: {result}")
        result = convert("./graphml/simple2.graphml", "./target/simple2.svg")
        print(f"[OK] Successfully converted to: {result}")
        result = convert("./graphml/simple1.graphml", "./target/simple1.svg")
        print(f"[OK] Successfully converted to: {result}")
    else:
        # Create argument parser
        parser = argparse.ArgumentParser(
            description='Convert GraphML file to SVG format',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
            Examples:
            python graphml2svg.py input.graphml output.svg
            python graphml2svg.py ./graphml/simple.graphml ./target/simple.svg
            '''
        )
        
        parser.add_argument(
            'input',
            metavar='INPUT',
            help='Path to the input GraphML file'
        )
        
        parser.add_argument(
            'output',
            metavar='OUTPUT',
            help='Path for the output SVG file'
        )
        
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        # Parse arguments
        args = parser.parse_args()
        
        input_file = args.input
        output_file = args.output
        
        # Validate input file exists
        if not os.path.isfile(input_file):
            print(f"[ERROR] Input file not found: {input_file}", file=sys.stderr)
            sys.exit(1)
        
        # Validate input file extension
        if not input_file.lower().endswith('.graphml'):
            print(f"[WARNING] Input file does not have .graphml extension: {input_file}", file=sys.stderr)
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                if args.verbose:
                    print(f"[INFO] Created output directory: {output_dir}")
            except Exception as e:
                print(f"[ERROR] Failed to create output directory: {e}", file=sys.stderr)
                sys.exit(1)
        
        # Convert GraphML to SVG
        try:
            if args.verbose:
                print(f"[INFO] Converting: {input_file} → {output_file}")
            
            result = convert(input_file, output_file)
            
            # Get file size for confirmation
            file_size = os.path.getsize(result)
            print(f"[OK] Successfully converted to: {result} ({file_size} bytes)")
            
            if args.verbose:
                print(f"[INFO] Conversion completed successfully")
            
            sys.exit(0)
            
        except FileNotFoundError as e:
            print(f"[ERROR] {str(e)}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Conversion failed: {str(e)}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)


