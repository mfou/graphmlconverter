#!/usr/bin/env python3
"""
Core GraphML processing library - Generic functions for parsing and coordinate calculations.

This module provides:
- XML parsing from yEd GraphML files
- Type definitions for GraphML structures
- Coordinate calculations (paths, labels, bounds)
- Helper functions for font/color/style handling

Can be reused by any tool: graphml2svg, graphml2jpg, graphml2png, etc.
"""

import xml.etree.ElementTree as ET
import math
import html.parser
import html
import re
from typing import Dict, List, Any, TypedDict, Tuple

# ═════════════════════════════════════════════════════════════════════════════
# TYPE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

class Geometry(TypedDict):
    """Geometry of a node or group: position and size in world coordinates."""
    x: float
    y: float
    width: float
    height: float


class EdgeLabel(TypedDict, total=False):
    """Edge label data."""
    text: str
    x: float
    y: float
    width: float
    height: float
    fontSize: float
    fontFamily: str
    fontStyle: str
    textColor: str
    lineColor: str
    backgroundColor: str
    
    # SmartEdgeLabelModelParameter
    ratio: float
    distance: float
    distanceToCenter: bool
    position: str
    segment: int
    alignment: str


class EdgePath(TypedDict):
    """Point on an edge path."""
    x: float
    y: float


class EdgeGeometry(TypedDict):
    """Edge geometry: start, end, and intermediate waypoints."""
    source_id: str
    target_id: str
    path_start: Tuple[float, float]
    path_points: List[Tuple[float, float]]
    path_end: Tuple[float, float]


class LabelPosition(TypedDict):
    """Calculated label position."""
    x: float
    y: float
    rect_x: float
    rect_y: float
    text_x: float
    text_y: float


# ═════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════

NAMESPACES = {
    'graphml': 'http://graphml.graphdrawing.org/xmlns',
    'y': 'http://www.yworks.com/xml/graphml',
    'yed': 'http://www.yworks.com/xml/yed/3',
    'svg': 'http://www.w3.org/2000/svg'
}

FONT_MAPPING = {
    'Dialog': 'sans-serif',
    'Arial': 'sans-serif',
    'Helvetica': 'sans-serif',
    'Verdana': 'sans-serif',
    'Georgia': 'serif',
    'Times': 'serif',
    'Courier': 'monospace',
    'Courier New': 'monospace',
    'Consolas': 'monospace',
}


# ═════════════════════════════════════════════════════════════════════════════
# COLOR & FONT UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

def convert_hex_color_to_rgba(color: str) -> str:
    """Convert hex color codes to RGB format (strip alpha if present)."""
    color = color.strip()
    if len(color) == 9 and color.startswith('#'):
        return color[:7]  # Strip alpha
    return color


def map_font_family(font_family: str) -> str:
    """Map yEd font family names to generic CSS font families."""
    return FONT_MAPPING.get(font_family, 'sans-serif')


def get_font_style_attributes(font_style: str) -> Tuple[str, str]:
    """Convert yEd font style to SVG font attributes (style, weight)."""
    font_style = font_style.lower()
    svg_font_style = 'normal'
    svg_font_weight = 'normal'
    
    if 'italic' in font_style:
        svg_font_style = 'italic'
    if 'bold' in font_style:
        svg_font_weight = 'bold'
    
    return (svg_font_style, svg_font_weight)


def get_text_anchor(alignment: str) -> str:
    """Convert yEd text alignment to SVG text-anchor attribute."""
    alignment = alignment.lower()
    mapping = {
        'left': 'start',
        'center': 'middle',
        'right': 'end'
    }
    return mapping.get(alignment, 'middle')


def get_line_style_attributes(line_type: str, line_width: float = 1.0) -> Dict[str, str]:
    """Convert GraphML line type to SVG stroke attributes."""
    dash_size = max(2.0, line_width * 3)
    gap_size = max(2.0, line_width * 2)
    
    styles = {
        'stroke-linecap': 'butt',
        'stroke-linejoin': 'miter',
        'stroke-miterlimit': '10'
    }
    
    if line_type == 'dashed':
        styles['stroke-dasharray'] = f'{dash_size},{gap_size}'
    elif line_type == 'dotted':
        dot_size = 0.1
        styles['stroke-dasharray'] = f'{dot_size},{gap_size}'
        styles['stroke-linecap'] = 'round'
    elif line_type == 'dashed_dotted':
        dot_size = 0.1
        styles['stroke-dasharray'] = f'{dash_size},{gap_size},{dot_size},{gap_size}'
        styles['stroke-linecap'] = 'round'
    
    return styles


# ═════════════════════════════════════════════════════════════════════════════
# PATH CALCULATIONS - Core geometry functions
# ═════════════════════════════════════════════════════════════════════════════

def build_edge_path(edge_start: Tuple[float, float], 
                   path_points: List[Dict[str, float]], 
                   edge_end: Tuple[float, float]) -> List[Tuple[float, float]]:
    """
    Build complete edge path: start → waypoints → end
    
    Args:
        edge_start: Start point (x, y) in world coordinates
        path_points: List of intermediate points [{'x': ..., 'y': ...}, ...]
        edge_end: End point (x, y) in world coordinates
    
    Returns:
        List of tuples [(x, y), ...] representing complete path
    """
    full_path = [edge_start]
    full_path.extend([(pt['x'], pt['y']) for pt in path_points])
    full_path.append(edge_end)
    return full_path


def calculate_path_segment_lengths(full_path: List[Tuple[float, float]]) -> Tuple[List[float], float]:
    """
    Calculate length of each path segment and total length.
    
    Returns:
        (segment_lengths, total_length)
    """
    segment_lengths = []
    total_length = 0.0
    
    for i in range(len(full_path) - 1):
        x1, y1 = full_path[i]
        x2, y2 = full_path[i + 1]
        seg_len = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        segment_lengths.append(seg_len)
        total_length += seg_len
    
    return segment_lengths, total_length


def find_position_on_path(full_path: List[Tuple[float, float]], 
                         ratio: float) -> Tuple[float, float, int]:
    """
    Find position at given ratio along path (0=start, 1=end).
    
    Returns:
        (x, y, segment_index)
    """
    if len(full_path) < 2:
        return (full_path[0][0], full_path[0][1], 0) if full_path else (0, 0, 0)
    
    segment_lengths, total_length = calculate_path_segment_lengths(full_path)
    
    if total_length == 0:
        return (full_path[0][0], full_path[0][1], 0)
    
    target_dist = total_length * ratio
    current_dist = 0.0
    segment_idx = 0
    
    for i, seg_len in enumerate(segment_lengths):
        if current_dist + seg_len >= target_dist:
            segment_idx = i
            break
        current_dist += seg_len
    
    seg_remaining = target_dist - current_dist
    x1, y1 = full_path[segment_idx]
    x2, y2 = full_path[segment_idx + 1]
    seg_len = segment_lengths[segment_idx]
    
    if seg_len > 0:
        t = seg_remaining / seg_len
    else:
        t = 0.0
    
    x_pos = x1 + t * (x2 - x1)
    y_pos = y1 + t * (y2 - y1)
    
    return x_pos, y_pos, segment_idx


def calculate_perpendicular_offset(x1: float, y1: float, 
                                  x2: float, y2: float, 
                                  distance: float) -> Tuple[float, float]:
    """
    Calculate perpendicular offset to a line segment.
    
    The perpendicular vector is rotated 90° counter-clockwise.
    Distance is inverted to match yEd behavior (positive = left of direction).
    
    Returns:
        (offset_x, offset_y)
    """
    edge_dx = x2 - x1
    edge_dy = y2 - y1
    edge_len = math.sqrt(edge_dx**2 + edge_dy**2)
    
    if edge_len == 0:
        return (0, 0)
    
    perp_dx = -edge_dy / edge_len
    perp_dy = edge_dx / edge_len
    
    # Invert distance to match yEd behavior
    offset_x = perp_dx * (-distance)
    offset_y = perp_dy * (-distance)
    
    return offset_x, offset_y


# ═════════════════════════════════════════════════════════════════════════════
# SVG PATH GENERATION - Edge smoothing and arrows
# ═════════════════════════════════════════════════════════════════════════════

def build_rounded_path(points: List[Dict[str, float]], radius: float = 5) -> str:
    """
    Build an SVG path with rounded corners at each waypoint.
    
    Creates smooth curves at corners using quadratic Bézier curves (Q command)
    to connect straight line segments with rounded corners.
    
    Args:
        points: List of points [{'x': float, 'y': float}, ...]
        radius: Radius of rounding at corners (in SVG units)
    
    Returns:
        SVG path data string for use with <path d="..."/>
    """
    if len(points) < 2:
        return f"M {points[0]['x']},{points[0]['y']}"
    
    if len(points) == 2:
        return f"M {points[0]['x']},{points[0]['y']} L {points[1]['x']},{points[1]['y']}"
    
    path_data = f"M {points[0]['x']},{points[0]['y']}"
    
    for i in range(1, len(points) - 1):
        prev_x, prev_y = points[i-1]['x'], points[i-1]['y']
        curr_x, curr_y = points[i]['x'], points[i]['y']
        next_x, next_y = points[i+1]['x'], points[i+1]['y']
        
        # Vector from prev to curr
        dx1 = curr_x - prev_x
        dy1 = curr_y - prev_y
        dist1 = math.sqrt(dx1**2 + dy1**2)
        
        # Vector from curr to next
        dx2 = next_x - curr_x
        dy2 = next_y - curr_y
        dist2 = math.sqrt(dx2**2 + dy2**2)
        
        # Normalize and scale by radius
        if dist1 > 0:
            offset1_x = (dx1 / dist1) * radius
            offset1_y = (dy1 / dist1) * radius
        else:
            offset1_x, offset1_y = 0, 0
        
        if dist2 > 0:
            offset2_x = (dx2 / dist2) * radius
            offset2_y = (dy2 / dist2) * radius
        else:
            offset2_x, offset2_y = 0, 0
        
        # Points for quadratic Bézier curve
        # Start: curr - offset1 (back along incoming direction)
        # Control: curr (the corner point)
        # End: curr + offset2 (forward along outgoing direction)
        path_data += f" L {curr_x - offset1_x},{curr_y - offset1_y}"
        path_data += f" Q {curr_x},{curr_y} {curr_x + offset2_x},{curr_y + offset2_y}"
    
    # Add final line segment
    path_data += f" L {points[-1]['x']},{points[-1]['y']}"
    
    return path_data


def create_arrow_path(x: float, y: float, angle: float, arrow_type: str, 
                      color: str, line_width: float = 1.0) -> str:
    """
    Create SVG path for an arrow marker at a specific position and angle.
    
    Args:
        x: X coordinate of arrow tip
        y: Y coordinate of arrow tip
        angle: Angle in degrees (0 = right, 90 = down, -90 = up, 180 = left)
        arrow_type: 'standard' | 'diamond' | 'circle' | 'none'
        color: Hex color code
        line_width: Line width to scale arrow proportionally
    
    Returns:
        SVG path element as string (full <path .../> or empty string if type='none')
    """
    if arrow_type == 'none':
        return ""
    
    angle_rad = math.radians(angle)
    
    if arrow_type == 'standard':
        # Standard arrow: convex triangle pointing in direction
        # Works for any angle using proper vector rotation
        arrow_size = 4.0
        
        # Direction vectors
        dir_x = math.cos(angle_rad)      # Forward direction
        dir_y = math.sin(angle_rad)
        perp_x = -math.sin(angle_rad)    # Perpendicular (left)
        perp_y = math.cos(angle_rad)
        
        # Arrow dimensions
        back_dist = arrow_size * 2
        corner_dist = arrow_size
        
        # 4 points forming the convex arrow
        # Tip at (x, y)
        tip_x, tip_y = x, y
        
        # Corner 1 (top): back + left
        corner1_x = x - back_dist * dir_x + corner_dist * perp_x
        corner1_y = y - back_dist * dir_y + corner_dist * perp_y
        
        # Middle point (creates convexity): 75% back toward back, centered
        mid_x = x - back_dist * 0.75 * dir_x
        mid_y = y - back_dist * 0.75 * dir_y
        
        # Corner 2 (bottom): back - left
        corner2_x = x - back_dist * dir_x - corner_dist * perp_x
        corner2_y = y - back_dist * dir_y - corner_dist * perp_y
        
        # Build path: tip → corner1 → mid → corner2 → close
        path = f'M {tip_x},{tip_y} L {corner1_x},{corner1_y} L {mid_x},{mid_y} L {corner2_x},{corner2_y} Z'
        return f'<path d="{path}" stroke="none" fill="{color}"/>'
    
    elif arrow_type == 'diamond':
        # Diamond shape with fixed size
        size = 2.8
        # Vertices of diamond
        back_x = x - size * math.cos(angle_rad)
        back_y = y - size * math.sin(angle_rad)
        
        perp_angle = angle_rad + math.pi / 2
        side1_x = x + size * math.cos(perp_angle) / 2
        side1_y = y + size * math.sin(perp_angle) / 2
        
        side2_x = x - size * math.cos(perp_angle) / 2
        side2_y = y - size * math.sin(perp_angle) / 2
        
        path = f'M {x},{y} L {side1_x},{side1_y} L {back_x},{back_y} L {side2_x},{side2_y} Z'
        return f'<path d="{path}" stroke="none" fill="{color}"/>'
    
    elif arrow_type == 'circle':
        # Circle marker with fixed size
        radius = 2.0
        return f'<circle cx="{x}" cy="{y}" r="{radius}" stroke="none" fill="{color}"/>'
    
    return ""


# ═════════════════════════════════════════════════════════════════════════════
# SAFE ZONE MODEL - SmartEdgeLabelModelParameter positioning
# ═════════════════════════════════════════════════════════════════════════════

def _get_segment_endpoints(segment_index: int,
                           source_center: Tuple[float, float],
                           target_center: Tuple[float, float],
                           path_points: List[Dict[str, float]]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Get correct start/end points for a segment.
    
    Segment 0: source → waypoint[0]
    Segment i: waypoint[i-1] → waypoint[i]
    Segment N: waypoint[N-1] → target
    
    Returns:
        (seg_start, seg_end) as tuples (x, y)
    """
    if not path_points:
        return (source_center, target_center)
    
    num_waypoints = len(path_points)
    
    if segment_index == 0:
        return (source_center, (path_points[0]['x'], path_points[0]['y']))
    elif segment_index <= num_waypoints - 1:
        return ((path_points[segment_index-1]['x'], path_points[segment_index-1]['y']),
                (path_points[segment_index]['x'], path_points[segment_index]['y']))
    elif segment_index == num_waypoints:
        return ((path_points[num_waypoints-1]['x'], path_points[num_waypoints-1]['y']), 
                target_center)
    else:
        return (source_center, target_center)


def _find_node_label_info(nodes: List[Dict[str, Any]], 
                         node_id: str) -> Dict[str, Any]:
    """
    Get complete node label information: position, dimensions, text.
    
    Returns:
        Dict with center, x, y, width, height, text
    """
    for node in nodes:
        if node.get('id') != node_id:
            continue
        
        if 'label' not in node:
            continue
        
        label = node['label']
        geom = node.get('geometry', {})
        
        label_x = label.get('x', 0.0)
        label_y = label.get('y', 0.0)
        label_width = label.get('width', 0.0)
        label_height = label.get('height', 0.0)
        
        # Absolute position = geom position + label relative position
        abs_x = geom.get('x', 0.0) + label_x
        abs_y = geom.get('y', 0.0) + label_y
        
        return {
            'center': (abs_x + label_width / 2, abs_y + label_height / 2),
            'x': abs_x,
            'y': abs_y,
            'width': label_width,
            'height': label_height,
            'text': label.get('text', '')
        }
    
    return None


def calculate_label_position_on_segment(segment_index: int,
                                       source_center: Tuple[float, float],
                                       target_center: Tuple[float, float],
                                       path_points: List[Dict[str, float]],
                                       ratio: float,
                                       distance: float) -> Tuple[float, float]:
    """
    Calculate label position on segment using Safe Zone Model.
    
    ALGORITHM:
    - Waypoints (segment boundaries) → NO distance offset
    - Nodes (source/target) → Apply distance offset for protection
    - Position interpolated at ratio within safe zone
    
    Args:
        segment_index: Which segment (0=source→waypoint[0], ...)
        source_center: Source node center
        target_center: Target node center
        path_points: Edge waypoints
        ratio: Position within safe zone (0.0-1.0)
        distance: Safe zone width (typically 30px)
    
    Returns:
        (label_x, label_y) position on segment
    """
    seg_start, seg_end = _get_segment_endpoints(segment_index, source_center, target_center, path_points)
    
    seg_start_x, seg_start_y = seg_start
    seg_end_x, seg_end_y = seg_end
    
    # Calculate normalized direction
    dx = seg_end_x - seg_start_x
    dy = seg_end_y - seg_start_y
    seg_length = math.sqrt(dx**2 + dy**2)
    
    if seg_length == 0:
        return (seg_start_x, seg_start_y)
    
    norm_dx = dx / seg_length
    norm_dy = dy / seg_length
    
    # Determine if endpoints are waypoints
    start_is_waypoint = segment_index > 0
    end_is_waypoint = segment_index < len(path_points)
    
    # Calculate safe zone start (P0)
    if start_is_waypoint:
        p0_x = seg_start_x
        p0_y = seg_start_y
    else:
        p0_x = seg_start_x + distance * norm_dx
        p0_y = seg_start_y + distance * norm_dy
    
    # Calculate safe zone end (P1)
    if end_is_waypoint:
        p1_x = seg_end_x
        p1_y = seg_end_y
    else:
        p1_x = seg_end_x - distance * norm_dx
        p1_y = seg_end_y - distance * norm_dy
    
    # Interpolate at ratio within safe zone
    label_x = p0_x + ratio * (p1_x - p0_x)
    label_y = p0_y + ratio * (p1_y - p0_y)
    
    return (label_x, label_y)


# ═════════════════════════════════════════════════════════════════════════════
# XML PARSING - Core GraphML extraction
# ═════════════════════════════════════════════════════════════════════════════

def parse_graphml(input_path: str) -> Dict[str, Any]:
    """
    Parse a yEd GraphML file and extract all structured data.
    
    Returns:
        Dict containing:
        - 'nodes': List of node dictionaries
        - 'shape_nodes': List of shape node dictionaries
        - 'groups': List of group node dictionaries
        - 'edges': List of edge dictionaries
        - 'resources': Dictionary of embedded SVG resources
    """
    tree = ET.parse(input_path)
    root = tree.getroot()
    
    # Find the node graphics key ID dynamically
    # Look for key with yfiles.type="nodegraphics"
    node_graphics_key = None
    for key_elem in root.findall('.//graphml:key', NAMESPACES):
        if (key_elem.get('for') == 'node' and 
            key_elem.get('yfiles.type') == 'nodegraphics'):
            node_graphics_key = key_elem.get('id')
            break
    
    # Fallback to 'd5' or 'd6' if not found (common yEd defaults)
    if node_graphics_key is None:
        node_graphics_key = 'd5'  # Most common in yEd files
    
    # Find resources key if it exists
    resources_key = None
    for key_elem in root.findall('.//graphml:key', NAMESPACES):
        if (key_elem.get('for') == 'graphml' and 
            key_elem.get('yfiles.type') == 'resources'):
            resources_key = key_elem.get('id')
            break
    
    # Extract resources (embedded SVGs)
    resources = {}
    if resources_key:
        for resource in root.findall('.//y:Resources/y:Resource', NAMESPACES):
            resource_id = resource.get('id')
            svg_text = resource.text
            if resource_id and svg_text:
                resources[resource_id] = clean_embedded_svg(svg_text)
    
    # Extract nodes
    nodes = []
    shape_nodes = []
    groups = []
    
    for node in root.findall('.//graphml:node', NAMESPACES):
        node_id = node.get('id')
        node_data = {'id': node_id}
        
        data_elem = node.find('.//graphml:data[@key="{}"]'.format(node_graphics_key), NAMESPACES)
        if data_elem is None:
            # Try alternative keys if the found one doesn't work
            for data_candidate in node.findall('.//graphml:data', NAMESPACES):
                key_attr = data_candidate.get('key')
                if key_attr and (key_attr == 'd5' or key_attr == 'd0' or key_attr.startswith('d')):
                    if data_candidate.find('.//y:ShapeNode', NAMESPACES) is not None or \
                       data_candidate.find('.//y:SVGNode', NAMESPACES) is not None or \
                       data_candidate.find('.//y:GroupNode', NAMESPACES) is not None:
                        data_elem = data_candidate
                        break
        
        if data_elem is None:
            continue
        
        # Extract SVGNode
        svg_node = data_elem.find('.//y:SVGNode', NAMESPACES)
        if svg_node is not None:
            # Parse SVGNode structure
            geom = svg_node.find('.//y:Geometry', NAMESPACES)
            if geom is not None:
                node_data['geometry'] = {
                    'x': float(geom.get('x', 0)),
                    'y': float(geom.get('y', 0)),
                    'width': float(geom.get('width', 0)),
                    'height': float(geom.get('height', 0))
                }
            
            # Extract labels
            label_elem = svg_node.find('.//y:NodeLabel', NAMESPACES)
            if label_elem is not None:
                node_data['label'] = {
                    'text': label_elem.text or '',
                    'x': float(label_elem.get('x', 0)),
                    'y': float(label_elem.get('y', 0)),
                    'width': float(label_elem.get('width', 0)),
                    'height': float(label_elem.get('height', 0)),
                    'fontSize': float(label_elem.get('fontSize', 12)),
                    'fontFamily': label_elem.get('fontFamily', 'Dialog'),
                    'fontStyle': label_elem.get('fontStyle', 'plain'),
                    'textColor': label_elem.get('textColor', '#000000'),
                    'backgroundColor': label_elem.get('backgroundColor', '#ffffff'),
                    'lineColor': label_elem.get('lineColor', '#000000')
                }
            
            # Extract embedded SVG content (SVGModel with SVGContent refid)
            svg_model = svg_node.find('.//y:SVGModel', NAMESPACES)
            if svg_model is not None:
                svg_content_elem = svg_model.find('.//y:SVGContent', NAMESPACES)
                if svg_content_elem is not None:
                    refid = svg_content_elem.get('refid')
                    if refid and refid in resources:
                        node_data['svg_content'] = resources[refid]
            
            nodes.append(node_data)
        
        # Extract ShapeNode
        shape_node = data_elem.find('.//y:ShapeNode', NAMESPACES)
        if shape_node is not None:
            # Parse ShapeNode structure
            geom = shape_node.find('.//y:Geometry', NAMESPACES)
            if geom is not None:
                node_data['geometry'] = {
                    'x': float(geom.get('x', 0)),
                    'y': float(geom.get('y', 0)),
                    'width': float(geom.get('width', 0)),
                    'height': float(geom.get('height', 0))
                }
            
            # Extract fill color
            fill = shape_node.find('.//y:Fill', NAMESPACES)
            if fill is not None:
                node_data['fill_color'] = fill.get('color', '#FFFFFF')
                node_data['fill_transparent'] = fill.get('transparent', 'false') == 'true'
                # BUGFIX: Respect hasColor attribute - if hasColor="false", don't fill
                node_data['fill_has_color'] = fill.get('hasColor', 'true') == 'true'
            else:
                node_data['fill_color'] = '#FFFFFF'
                node_data['fill_transparent'] = False
                node_data['fill_has_color'] = True
            
            # Extract border style
            border = shape_node.find('.//y:BorderStyle', NAMESPACES)
            if border is not None:
                node_data['border_color'] = border.get('color', '#000000')
                node_data['border_width'] = float(border.get('width', '1.0'))
                node_data['border_type'] = border.get('type', 'line')
                # BUGFIX: Respect hasColor attribute - if hasColor="false", don't draw border
                node_data['border_has_color'] = border.get('hasColor', 'true') == 'true'
            else:
                node_data['border_color'] = '#000000'
                node_data['border_width'] = 1.0
                node_data['border_type'] = 'line'
                node_data['border_has_color'] = True
            
            # Extract shape type
            shape = shape_node.find('.//y:Shape', NAMESPACES)
            if shape is not None:
                node_data['shape_type'] = shape.get('type', 'rectangle')
            else:
                node_data['shape_type'] = 'rectangle'
            
            # Extract all labels (multiple labels allowed per ShapeNode)
            label_elements = shape_node.findall('.//y:NodeLabel', NAMESPACES)
            if label_elements:
                node_data['labels'] = []
                for label_elem in label_elements:
                    # Skip labels with hasText="false" (invisible labels)
                    if label_elem.get('hasText', 'true') == 'false':
                        continue
                    
                    node_data['labels'].append({
                        'text': label_elem.text or '',
                        'x': float(label_elem.get('x', 0)),
                        'y': float(label_elem.get('y', 0)),
                        'width': float(label_elem.get('width', 0)),
                        'height': float(label_elem.get('height', 0)),
                        'fontSize': float(label_elem.get('fontSize', 12)),
                        'fontFamily': label_elem.get('fontFamily', 'Dialog'),
                        'fontStyle': label_elem.get('fontStyle', 'plain'),
                        'textColor': label_elem.get('textColor', '#000000'),
                        'backgroundColor': label_elem.get('backgroundColor', '#ffffff'),
                        'lineColor': label_elem.get('lineColor', '#000000'),
                        'alignment': label_elem.get('alignment', 'center'),
                        'modelName': label_elem.get('modelName', 'internal'),
                        'modelPosition': label_elem.get('modelPosition', 'c'),
                        'hasLineColor': label_elem.get('hasLineColor', 'false') == 'true'
                    })
            
            shape_nodes.append(node_data)
        
        # Extract GroupNode
        group_node = data_elem.find('.//y:GroupNode', NAMESPACES)
        realizers = data_elem.find('.//y:Realizers', NAMESPACES)
        if realizers is not None:
            group_node = realizers.find('.//y:GroupNode', NAMESPACES)
        
        if group_node is not None:
            geom = group_node.find('.//y:Geometry', NAMESPACES)
            if geom is not None:
                node_data['geometry'] = {
                    'x': float(geom.get('x', 0)),
                    'y': float(geom.get('y', 0)),
                    'width': float(geom.get('width', 0)),
                    'height': float(geom.get('height', 0))
                }
            
            # Extract Fill color for group body
            fill = group_node.find('.//y:Fill', NAMESPACES)
            if fill is not None:
                node_data['body_fill_color'] = fill.get('color', '#F0F0F0')
                node_data['fill_transparent'] = fill.get('transparent', 'false') == 'true'
                # BUGFIX: Respect hasColor attribute - if hasColor="false", don't fill
                node_data['fill_has_color'] = fill.get('hasColor', 'true') == 'true'
            else:
                node_data['body_fill_color'] = '#F0F0F0'
                node_data['fill_has_color'] = True
            
            # Extract BorderStyle color and width
            border = group_node.find('.//y:BorderStyle', NAMESPACES)
            if border is not None:
                node_data['body_border_color'] = border.get('color', '#999999')
                node_data['body_border_width'] = float(border.get('width', '1.0'))
                node_data['body_border_type'] = border.get('type', 'line')
                # BUGFIX: Respect hasColor attribute - if hasColor="false", don't draw border
                node_data['border_has_color'] = border.get('hasColor', 'true') == 'true'
            else:
                node_data['body_border_color'] = '#999999'
                node_data['body_border_width'] = 1.0
                node_data['body_border_type'] = 'line'
                node_data['border_has_color'] = True
            
            # Extract header fill color and all labels (NodeLabel)
            label_elements = group_node.findall('.//y:NodeLabel', NAMESPACES)
            if label_elements:
                # Use first label's background color for header
                node_data['header_fill_color'] = label_elements[0].get('backgroundColor', '#CCCCCC')
                
                # Extract all label properties
                node_data['labels'] = []
                for label in label_elements:
                    # Skip labels with hasText="false"
                    if label.get('hasText', 'true') == 'false':
                        continue
                    
                    node_data['labels'].append({
                        'text': label.text or '',
                        'fontFamily': label.get('fontFamily', 'Dialog'),
                        'fontSize': int(label.get('fontSize', '12')),
                        'fontStyle': label.get('fontStyle', 'plain'),
                        'textColor': label.get('textColor', '#000000'),
                        'alignment': label.get('alignment', 'center'),
                        'backgroundColor': label.get('backgroundColor', '#CCCCCC'),
                        'underlined': label.get('underline', 'false') == 'true',
                        'hasLineColor': label.get('hasLineColor', 'false') == 'true',
                        'modelName': label.get('modelName', 'internal'),
                        'modelPosition': label.get('modelPosition', 't')
                    })
            else:
                node_data['header_fill_color'] = '#CCCCCC'
            
            groups.append(node_data)
    
    # Extract edges
    edges = []
    for edge in root.findall('.//graphml:edge', NAMESPACES):
        edge_id = edge.get('id')
        source = edge.get('source')
        target = edge.get('target')
        edge_data = {'id': edge_id, 'source': source, 'target': target}
        
        # Extract PolyLineEdge
        poly_edge = edge.find('.//y:PolyLineEdge', NAMESPACES)
        if poly_edge is not None:
            # Extract Path element with sx, sy, tx, ty offsets
            path_elem = poly_edge.find('.//y:Path', NAMESPACES)
            if path_elem is not None:
                edge_data['path_sx'] = float(path_elem.get('sx', 0))
                edge_data['path_sy'] = float(path_elem.get('sy', 0))
                edge_data['path_tx'] = float(path_elem.get('tx', 0))
                edge_data['path_ty'] = float(path_elem.get('ty', 0))
            else:
                edge_data['path_sx'] = 0.0
                edge_data['path_sy'] = 0.0
                edge_data['path_tx'] = 0.0
                edge_data['path_ty'] = 0.0
            
            # Extract path points
            path_points = []
            for point in poly_edge.findall('.//y:Point', NAMESPACES):
                path_points.append({
                    'x': float(point.get('x', 0)),
                    'y': float(point.get('y', 0))
                })
            edge_data['path_points'] = path_points
            
            # Extract line style
            line_style = poly_edge.find('.//y:LineStyle', NAMESPACES)
            if line_style is not None:
                edge_data['line_type'] = line_style.get('type', 'line')
                edge_data['line_width'] = float(line_style.get('width', 1.0))
                edge_data['line_color'] = line_style.get('color', '#000000')
            
            # Extract bend style (smoothed flag)
            bend_style = poly_edge.find('.//y:BendStyle', NAMESPACES)
            if bend_style is not None:
                edge_data['smoothed'] = bend_style.get('smoothed', 'false').lower() == 'true'
            else:
                edge_data['smoothed'] = False
            
            # Extract arrows (source and target)
            arrows = poly_edge.find('.//y:Arrows', NAMESPACES)
            if arrows is not None:
                edge_data['arrow_source'] = arrows.get('source', 'none')
                edge_data['arrow_target'] = arrows.get('target', 'none')
            else:
                edge_data['arrow_source'] = 'none'
                edge_data['arrow_target'] = 'none'
            
            # Extract edge labels
            labels = []
            for label_elem in poly_edge.findall('.//y:EdgeLabel', NAMESPACES):
                label_data = {
                    'text': label_elem.text or '',
                    'x': float(label_elem.get('x', 0)),
                    'y': float(label_elem.get('y', 0)),
                    'width': float(label_elem.get('width', 0)),
                    'height': float(label_elem.get('height', 0)),
                    'fontSize': float(label_elem.get('fontSize', 12)),
                    'fontFamily': label_elem.get('fontFamily', 'Dialog'),
                    'fontStyle': label_elem.get('fontStyle', 'plain'),
                    'textColor': label_elem.get('textColor', '#000000'),
                    'backgroundColor': label_elem.get('backgroundColor', '#ffffff'),
                    'lineColor': label_elem.get('lineColor', '#000000'),
                    'alignment': label_elem.get('alignment', 'center')
                }
                
                # Extract SmartEdgeLabelModelParameter if present
                smart_model = label_elem.find('.//y:SmartEdgeLabelModelParameter', NAMESPACES)
                if smart_model is not None:
                    label_data['smart_edge_label_model_parameter'] = {
                        'segment': int(smart_model.get('segment', 0)),
                        'ratio': float(smart_model.get('ratio', 0.5)),
                        'distance': float(smart_model.get('distance', 30.0)),
                        'distanceToCenter': smart_model.get('distanceToCenter', 'false').lower() == 'true'
                    }
                
                labels.append(label_data)
            
            edge_data['labels'] = labels
        
        edges.append(edge_data)
    
    return {
        'nodes': nodes,
        'shape_nodes': shape_nodes,
        'groups': groups,
        'edges': edges,
        'resources': resources
    }


def clean_embedded_svg(svg_content: str) -> str:
    """Clean embedded SVG content by decoding HTML entities and removing XML declarations and comments."""
    import html
    # First decode HTML entities (&lt; -> <, &gt; -> >, etc.)
    svg_content = html.unescape(svg_content)
    # Remove XML declarations
    svg_content = re.sub(r'<\?xml[^?]*\?>', '', svg_content)
    # Remove HTML/XML comments (handle multiline)
    svg_content = re.sub(r'<!--.*?-->', '', svg_content, flags=re.DOTALL)
    # CRITICAL: Remove all <clipPath> elements (the entire clipPath definition block)
    # This prevents the embedded SVG's internal clipPath from interfering with our clipping
    # We use a non-greedy match to correctly handle multiple clipPath elements
    svg_content = re.sub(r'<clipPath[^>]*>.*?</clipPath>', '', svg_content, flags=re.DOTALL)
    # CRITICAL: Remove all clip-path="url(#...)" attributes from elements
    # This removes references to the old clipPath definitions
    svg_content = re.sub(r'\s*clip-path="[^"]*"', '', svg_content)
    # Clean up whitespace but preserve structure
    svg_content = '\n'.join(line.strip() for line in svg_content.split('\n') if line.strip())
    return svg_content


# ═════════════════════════════════════════════════════════════════════════════
# BOUNDS CALCULATIONS
# ═════════════════════════════════════════════════════════════════════════════

def calculate_edges_labels_bounds(edges: List[Dict[str, Any]], 
                                  node_map: Dict[str, Dict[str, Any]],
                                  nodes: List[Dict[str, Any]] = None,
                                  groups: List[Dict[str, Any]] = None) -> Tuple[List[float], List[float]]:
    """
    Calculate bounds for edges, labels, and embedded SVG content.
    
    Args:
        edges: List of edges
        node_map: Mapping of nodes to their geometries
        nodes: Optional list of nodes to include labels and embedded SVG
        groups: Optional list of groups
    
    Returns:
        (x_coords, y_coords) - Lists of all x and y coordinates
    """
    x_coords = []
    y_coords = []
    
    for edge in edges:
        source_id = edge.get('source')
        target_id = edge.get('target')
        
        # Get path points
        path_points = edge.get('path_points', [])
        
        # Add path point coordinates
        for pt in path_points:
            if isinstance(pt, dict) and 'x' in pt and 'y' in pt:
                x_coords.append(pt['x'])
                y_coords.append(pt['y'])
        
        # BUGFIX: Include edge labels in bounds calculation
        # Edge labels are positioned relative to the source node center and must be included
        # in the SVG canvas bounds calculation to prevent clipping
        if source_id in node_map:
            source_geom = node_map[source_id]
            source_center_x = source_geom['x'] + source_geom['width'] / 2
            source_center_y = source_geom['y'] + source_geom['height'] / 2
            
            # Process all labels for this edge
            labels = edge.get('labels', [])
            if not labels and 'label' in edge:
                labels = [edge['label']]
            
            for label in labels:
                if not label or not isinstance(label, dict):
                    continue
                
                # Calculate label position (absolute coordinates)
                label_rel_x = label.get('x', 0.0)
                label_rel_y = label.get('y', 0.0)
                label_width = label.get('width', 0.0)
                label_height = label.get('height', 0.0)
                
                # Absolute label position
                label_abs_x = source_center_x + label_rel_x
                label_abs_y = source_center_y + label_rel_y
                
                # Add label bounds
                x_coords.extend([
                    label_abs_x,
                    label_abs_x + label_width
                ])
                y_coords.extend([
                    label_abs_y,
                    label_abs_y + label_height
                ])
    
    # Include node labels in bounds calculation
    # ONLY if they are NOT already included in a parent group geometry
    if nodes:
        # Build a set of node IDs that are inside groups
        grouped_node_ids = set()
        if groups:
            for group in groups:
                group_id = group.get('id', '')
                # Find all nodes whose ID starts with group_id::
                for node in nodes:
                    node_id = node.get('id', '')
                    if node_id.startswith(group_id + '::'):
                        grouped_node_ids.add(node_id)
        
        for node in nodes:
            if 'geometry' not in node or 'label' not in node:
                continue
            
            # Skip if this node is inside a group (labels already included in group geometry)
            if node['id'] in grouped_node_ids:
                continue
            
            geom = node['geometry']
            label = node['label']
            
            # Skip if no text
            if not label.get('text'):
                continue
            
            # Calculate label position (same logic as draw_node_labels)
            node_x = geom['x']
            node_y = geom['y']
            node_width = geom['width']
            node_height = geom['height']
            
            # Label position (centered horizontally, below the node)
            label_x = node_x + node_width / 2
            label_y = node_y + node_height + label.get('font_size', 12) + 4
            
            # Estimate label width/height from text length
            label_text = label.get('text', '')
            # Rough estimate: each character is ~6px wide, height is font_size
            label_width = max(len(label_text) * 6, 30)  # min 30px
            label_height = label.get('font_size', 12) * 1.5  # Add line height
            
            # Add label bounds to coordinates
            x_coords.extend([
                label_x - label_width / 2,
                label_x + label_width / 2
            ])
            y_coords.extend([
                label_y - label_height / 2,
                label_y + label_height / 2
            ])
    
    # Include embedded SVG content bounds
    # Each node can have embedded SVG with its own coordinate system
    if nodes:
        import re
        for node in nodes:
            if 'svg_content' not in node or 'geometry' not in node:
                continue
            
            svg_content = node['svg_content']
            geom = node['geometry']
            node_x = geom['x']
            node_y = geom['y']
            node_width = geom['width']
            node_height = geom['height']
            
            # Extract viewBox from embedded SVG
            # Format: viewBox="0 0 width height"
            viewbox_match = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_content)
            if viewbox_match:
                viewbox_str = viewbox_match.group(1)
                try:
                    viewbox_parts = viewbox_str.split()
                    if len(viewbox_parts) >= 4:
                        vb_x, vb_y, vb_w, vb_h = map(float, viewbox_parts[:4])
                        
                        # The embedded SVG is placed at (node_x, node_y) with size (node_width, node_height)
                        # Its content spans from vb_x to vb_x+vb_w, vb_y to vb_y+vb_h in its coordinate system
                        # We need to map this to world coordinates
                        
                        # Scale factors
                        scale_x = node_width / vb_w if vb_w != 0 else 1
                        scale_y = node_height / vb_h if vb_h != 0 else 1
                        
                        # World coordinates of viewBox corners
                        world_x_min = node_x + (vb_x * scale_x)
                        world_x_max = node_x + ((vb_x + vb_w) * scale_x)
                        world_y_min = node_y + (vb_y * scale_y)
                        world_y_max = node_y + ((vb_y + vb_h) * scale_y)
                        
                        x_coords.extend([world_x_min, world_x_max])
                        y_coords.extend([world_y_min, world_y_max])
                except ValueError:
                    pass
    
    return x_coords, y_coords


# ═════════════════════════════════════════════════════════════════════════════
# HTML PARSING for node/edge labels
# ═════════════════════════════════════════════════════════════════════════════

class HTMLTableParser(html.parser.HTMLParser):
    """Parse HTML content to extract table data and styled text."""
    
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = None
        self.current_cell = None
        self.current_cell_segments = []
        self.simple_text_segments = []
        self.simple_text_lines = []
        self.current_color = None
        self.current_is_bold = False
        self.current_is_italic = False
        self.text_buffer = ''
    
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        
        if tag == 'table':
            self.rows = []
        elif tag == 'tr':
            self.current_row = []
            self.rows.append(self.current_row)
        elif tag == 'td':
            self.current_cell = []
            self.current_cell_segments = []
        elif tag == 'font':
            if 'color' in attrs_dict:
                self.current_color = attrs_dict['color']
        elif tag in ('b', 'strong'):
            self.current_is_bold = True
        elif tag in ('i', 'em'):
            self.current_is_italic = True
        elif tag == 'br':
            if self.text_buffer or self.simple_text_segments:
                self.simple_text_lines.append(self.simple_text_segments[:])
                self.simple_text_segments = []
            self.text_buffer = ''
    
    def handle_endtag(self, tag):
        tag = tag.lower()
        
        if tag == 'font':
            self.current_color = None
        elif tag in ('b', 'strong'):
            # When closing a bold tag, flush current text buffer with bold flag still active
            if self.text_buffer and self.current_cell is not None:
                self.current_cell_segments.append({
                    'text': self.text_buffer,
                    'color': self.current_color,
                    'is_bold': True,  # Capture bold state BEFORE clearing it
                    'is_italic': self.current_is_italic
                })
                self.text_buffer = ''
            self.current_is_bold = False
        elif tag in ('i', 'em'):
            # When closing an italic tag, flush current text buffer with italic flag still active
            if self.text_buffer and self.current_cell is not None:
                self.current_cell_segments.append({
                    'text': self.text_buffer,
                    'color': self.current_color,
                    'is_bold': self.current_is_bold,
                    'is_italic': True  # Capture italic state BEFORE clearing it
                })
                self.text_buffer = ''
            self.current_is_italic = False
        elif tag == 'td':
            if self.text_buffer:
                self.current_cell_segments.append({
                    'text': self.text_buffer,
                    'color': self.current_color,
                    'is_bold': self.current_is_bold,
                    'is_italic': self.current_is_italic
                })
                self.text_buffer = ''
            
            if self.current_cell is not None:
                self.current_cell.append(self.current_cell_segments)
                self.current_row.append({'segments': self.current_cell_segments, 'text': ''})
            
            self.current_cell_segments = []
    
    def handle_data(self, data):
        if data.strip():
            if self.current_cell is not None:
                self.text_buffer += data
            else:
                self.simple_text_segments.append({
                    'text': data,
                    'color': self.current_color,
                    'is_bold': self.current_is_bold,
                    'is_italic': self.current_is_italic
                })


def parse_html_label(html_text: str) -> Dict[str, Any]:
    """Parse HTML content from a label and extract table or text with styling."""
    try:
        html_text = html.unescape(html_text)
    except:
        pass
    
    parser = HTMLTableParser()
    try:
        parser.feed(html_text)
    except:
        pass
    
    # If we found table rows, return table data
    if parser.rows:
        return {
            'is_table': True,
            'rows': parser.rows
        }
    
    # Process simple text segments into lines
    lines_result = []
    
    if parser.simple_text_lines:
        lines_result = parser.simple_text_lines
    
    if parser.simple_text_segments:
        lines_result.append(parser.simple_text_segments)
    
    # Fallback: remove HTML tags manually
    if not lines_result:
        clean_text = re.sub(r'<[^>]+>', '', html_text).strip()
        if clean_text:
            lines_result = [[{'text': clean_text, 'color': None, 'is_bold': False, 'is_italic': False}]]
    
    if not lines_result:
        lines_result = [[{'text': '', 'color': None, 'is_bold': False, 'is_italic': False}]]
    
    return {
        'is_table': False,
        'lines': lines_result
    }
