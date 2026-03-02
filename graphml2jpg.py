"""
Analyse visuelle améliorée du fichier GraphML avec meilleure clarté et lisibilité.
"""

import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple
import math

# Import core functions and types from graphmlcore
from graphmlcore import (
    parse_graphml,
    calculate_label_position_on_segment,
    _get_segment_endpoints,
    _find_node_label_info,
    build_edge_path,
    find_position_on_path,
    convert_hex_color_to_rgba,
    map_font_family,
    get_font_style_attributes,
    NAMESPACES,
    Geometry,
    EdgeLabel,
)



# Configuration des couleurs
COLORS = {
    'group': (50, 150, 255),      # Bleu
    'node': (0, 200, 0),           # Vert
    'edge': (150, 0, 255),         # Violet
    'control_point': (255, 0, 0),  # Rouge
    'label': (200, 0, 0),          # Rouge foncé
    'text': (0, 0, 0),             # Noir
    'bg': (255, 255, 255),         # Blanc
    'grid': (220, 220, 220),       # Gris clair
}

class ImprovedGraphMLVisualizer:
    def __init__(self, graphml_file: str, scale: float = 2.0):
        self.graphml_file = graphml_file
        self.scale = scale
        self.tree = ET.parse(graphml_file)
        self.root = self.tree.getroot()
        
        self.nodes = []
        self.groups = []
        self.edges = []
        self.edge_labels = []
        
        self.min_x = float('inf')
        self.min_y = float('inf')
        self.max_x = float('-inf')
        self.max_y = float('-inf')
    
    def _get_best_node_label(self, parent_elem) -> str:
        """
        Extract the best NodeLabel from a parent element.
        Can handle multiple NodeLabel elements (e.g., n3::n4 in simple3.graphml).
        
        Strategy:
        1. Find ALL NodeLabel elements
        2. Filter: exclude labels with hasText="false" or empty text
        3. Prefer: label with longest non-empty text
        4. Fallback: return first visible label
        5. Default: return empty string
        
        Returns:
            Best label text or empty string
        """
        labels = parent_elem.findall('.//y:NodeLabel', NAMESPACES)
        if not labels:
            return ''
        
        best_text = ''
        best_length = 0
        
        for label_elem in labels:
            # Check if hasText="false" attribute
            has_text = label_elem.get('hasText', 'true')
            if has_text == 'false':
                continue
            
            # Get text content
            label_text = (label_elem.text or '').strip()
            
            # Prefer label with non-empty text
            if label_text and len(label_text) > best_length:
                best_text = label_text
                best_length = len(label_text)
        
        return best_text
    
    def _get_best_node_label_element(self, parent_elem):
        """
        Extract the best NodeLabel ELEMENT from a parent element.
        Can handle multiple NodeLabel elements (e.g., n3::n4 in simple3.graphml).
        
        Strategy:
        1. Find ALL NodeLabel elements
        2. Filter: exclude labels with hasText="false"
        3. Prefer: label with non-empty text
        4. Fallback: return first label with largest dimensions (width * height)
        5. Default: return first label or None
        
        Returns:
            Best NodeLabel element or None
        """
        labels = parent_elem.findall('.//y:NodeLabel', NAMESPACES)
        if not labels:
            return None
        
        # First pass: find label with non-empty text
        best_elem = None
        best_text_length = 0
        
        for label_elem in labels:
            # Check if hasText="false" attribute
            has_text = label_elem.get('hasText', 'true')
            if has_text == 'false':
                continue
            
            # Get text content
            label_text = (label_elem.text or '').strip()
            
            # Prefer label with non-empty text
            if label_text and len(label_text) > best_text_length:
                best_elem = label_elem
                best_text_length = len(label_text)
        
        # If no text-based label found, return first non-hasText=false label
        if best_elem is None:
            for label_elem in labels:
                has_text = label_elem.get('hasText', 'true')
                if has_text != 'false':
                    best_elem = label_elem
                    break
        
        # If still nothing, return first label
        if best_elem is None and labels:
            best_elem = labels[0]
        
        return best_elem
        
    def parse(self):
        """Parse the GraphML file"""
        self._extract_nodes()
        self._extract_groups()
        self._extract_edges()
        self._extract_edge_labels()
        self._calculate_bounds()
    
    def _extract_nodes(self):
        """Extract node information"""
        for node in self.root.findall('.//graphml:node', NAMESPACES):
            if node.get('yfiles.foldertype') == 'group':
                continue
            
            node_id = node.get('id')
            label_text = ''
            geom = None
            node_type = None
            
            # Check for SVGNode
            svg_node = node.find('.//y:SVGNode', NAMESPACES)
            if svg_node is not None:
                geom = svg_node.find('.//y:Geometry', NAMESPACES)
                node_type = 'SVGNode'
                label_text = self._get_best_node_label(svg_node)
            
            # Check for ShapeNode
            if geom is None:
                shape_node = node.find('.//y:ShapeNode', NAMESPACES)
                if shape_node is not None:
                    geom = shape_node.find('.//y:Geometry', NAMESPACES)
                    node_type = 'ShapeNode'
                    label_text = self._get_best_node_label(shape_node)
            
            if geom is not None:
                x = float(geom.get('x', 0))
                y = float(geom.get('y', 0))
                w = float(geom.get('width', 0))
                h = float(geom.get('height', 0))
                
                self.nodes.append({
                    'id': node_id,
                    'x': x,
                    'y': y,
                    'width': w,
                    'height': h,
                    'label': label_text,
                    'type': node_type
                })
                
                self._update_bounds(x, y, x + w, y + h)
    
    def _extract_groups(self):
        """Extract group node information"""
        for node in self.root.findall('.//graphml:node[@yfiles.foldertype="group"]', NAMESPACES):
            node_id = node.get('id')
            
            group_node = node.find('.//y:ProxyAutoBoundsNode/y:Realizers/y:GroupNode[1]', NAMESPACES)
            if group_node is not None:
                label_text = self._get_best_node_label(group_node)
                
                geom = group_node.find('.//y:Geometry', NAMESPACES)
                if geom is not None:
                    x = float(geom.get('x', 0))
                    y = float(geom.get('y', 0))
                    w = float(geom.get('width', 0))
                    h = float(geom.get('height', 0))
                    
                    self.groups.append({
                        'id': node_id,
                        'x': x,
                        'y': y,
                        'width': w,
                        'height': h,
                        'label': label_text,
                        'type': 'GroupNode'
                    })
                    
                    self._update_bounds(x, y, x + w, y + h)
    
    def _extract_edges(self):
        """Extract edge information"""
        for edge in self.root.findall('.//graphml:edge', NAMESPACES):
            edge_id = edge.get('id')
            source = edge.get('source')
            target = edge.get('target')
            
            path_data = None
            edge_labels_data = []
            
            poly_edge = edge.find('.//graphml:data/y:PolyLineEdge', NAMESPACES)
            if poly_edge is not None:
                # Extract path and label data
                path_data = self._extract_edge_path_data(poly_edge)
                
                # Extract and calculate label coordinates
                edge_labels_data = self._extract_and_calculate_edge_labels(
                    poly_edge, source, target, path_data
                )
            
            self.edges.append({
                'id': edge_id,
                'source': source,
                'target': target,
                'path': path_data,
                'labels': edge_labels_data
            })
    
    def _extract_edge_path_data(self, poly_edge) -> Dict:
        """
        Extract path data from a PolyLineEdge element.
        
        Returns:
            Dict containing 'points' (list of waypoints) and path offsets (sx, sy, tx, ty)
        """
        path_elem = poly_edge.find('.//y:Path', NAMESPACES)
        if path_elem is None:
            return None
        
        points = []
        for pt in path_elem.findall('.//y:Point', NAMESPACES):
            px = float(pt.get('x', 0))
            py = float(pt.get('y', 0))
            points.append((px, py))
            self._update_bounds(px, py, px, py)
        
        path_data = {
            'points': points,
            'sx': float(path_elem.get('sx', 0)),
            'sy': float(path_elem.get('sy', 0)),
            'tx': float(path_elem.get('tx', 0)),
            'ty': float(path_elem.get('ty', 0))
        }
        
        return path_data
    
    def _extract_and_calculate_edge_labels(self, poly_edge, source: str, target: str, 
                                          path_data: Dict) -> List[Dict]:
        """
        Extract EdgeLabel elements and calculate their absolute coordinates.
        
        SIMPLIFIED: Raw coordinates calculation only (no étape 4 perpendicular vector adjustment)
        Edge label absolute position = reference_point + relative_offset
        
        Parameters:
            poly_edge: The PolyLineEdge XML element
            source: Source node ID
            target: Target node ID
            path_data: Path data with points and offsets
            
        Returns:
            List of label attribute dictionaries with calculated absolute coordinates
        """
        edge_labels_data = []
        
        # Extract SmartEdgeLabelModel defaultDistance
        smart_label_model = poly_edge.find('.//y:SmartEdgeLabelModel', NAMESPACES)
        default_distance = None
        if smart_label_model is not None:
            default_distance = float(smart_label_model.get('defaultDistance', 10.0))
        
        # Get source and target node centers for label coordinate calculation
        source_center = self._find_node_center(source)
        target_center = self._find_node_center(target)
        
        # Get source node label center for overlap detection
        source_node_label_center = self._find_node_label_center(source)
        
        # Extract and process each EdgeLabel
        for edge_label in poly_edge.findall('.//y:EdgeLabel', NAMESPACES):
            # Extract raw attributes from XML
            label_attrs = self._extract_label_attributes(edge_label, default_distance)
            
            # Convert string coordinate attributes to float for drawing
            label_attrs['x'] = float(label_attrs.get('x', 0))
            label_attrs['y'] = float(label_attrs.get('y', 0))
            label_attrs['width'] = float(label_attrs.get('width', 0))
            label_attrs['height'] = float(label_attrs.get('height', 0))
            
            # ÉTAPE 1: Stockage des données brutes sans offset
            # Les offsets seront calculés en ÉTAPE 2 (_apply_edge_label_adjustments)
            # Cela permet d'avoir une source unique de vérité pour les calculs
            
            # Store SmartEdgeLabelModelParameter info for ÉTAPE 2
            if 'smart_edge_label_model_parameter' in label_attrs:
                smart_params = label_attrs['smart_edge_label_model_parameter']
                label_attrs['smart_segment'] = int(smart_params.get('segment', 0))
                label_attrs['smart_ratio'] = float(smart_params.get('ratio', 0.5))
                label_attrs['smart_distance'] = float(smart_params.get('distance', 0.0))
            
            # Position brute du label (sera ajustée en ÉTAPE 2)
            # Utiliser juste les offsets du label XML sans path offsets
            label_attrs['abs_x'] = label_attrs['x']
            label_attrs['abs_y'] = label_attrs['y']
            
            # Stocker les données du chemin pour ÉTAPE 2 (nécessaire pour SmartEdgeLabelModel)
            label_attrs['path_data'] = path_data
            label_attrs['source_id'] = source
            label_attrs['target_id'] = target
            
            # IMPORTANT: Ajouter à la liste des labels
            edge_labels_data.append(label_attrs)
        
        return edge_labels_data
    
    def _extract_label_attributes(self, edge_label, default_distance: float) -> Dict:
        """
        Extract all attributes from an EdgeLabel element.
        
        Parameters:
            edge_label: The EdgeLabel XML element
            default_distance: Default distance from SmartEdgeLabelModel
            
        Returns:
            Dictionary with label attributes and model parameters
        """
        label_attrs = {}
        
        # Get all XML attributes
        for attr_name, attr_value in edge_label.attrib.items():
            label_attrs[attr_name] = attr_value
        
        # Extract text content
        label_text = edge_label.text or ''
        label_attrs['text'] = label_text
        
        # Extract y:ModelParameter if present
        model_param = edge_label.find('.//y:ModelParameter', NAMESPACES)
        if model_param is not None:
            label_attrs['model_parameter'] = {}
            for attr_name, attr_value in model_param.attrib.items():
                label_attrs['model_parameter'][attr_name] = attr_value
        
        # Extract y:SmartEdgeLabelModelParameter if present
        smart_edge_param = edge_label.find('.//y:SmartEdgeLabelModelParameter', NAMESPACES)
        if smart_edge_param is not None:
            label_attrs['smart_edge_label_model_parameter'] = {}
            for attr_name, attr_value in smart_edge_param.attrib.items():
                label_attrs['smart_edge_label_model_parameter'][attr_name] = attr_value
        
        # Store the default distance
        label_attrs['default_distance'] = default_distance
        
        return label_attrs
    
    def _get_segment_endpoints(self, segment_index: int, source_center: Tuple,
                              target_center: Tuple, path_data: Dict, 
                              source_node_label_center: Tuple = None) -> Tuple[float, float, float, float]:
        """
        Get the start and end points of a segment.
        
        Segment indexing:
        - Segment 0: from (source_center + offsets) to first waypoint
                     OR from node label center if label overlaps segment
        - Segment 1..N-1: from waypoint[i-1] to waypoint[i]
        - Segment N: from last waypoint to (target_center + offsets)
        
        Parameters:
            segment_index: Index of the segment
            source_center: (x, y) of source node center
            target_center: (x, y) of target node center
            path_data: Path data containing waypoints and offsets (sx, sy, tx, ty)
            source_node_label_center: (x, y) of source node label center (absolute coordinates)
                                    Used for segment 0 if label overlaps segment
            
        Returns:
            Tuple of (seg_start_x, seg_start_y, seg_end_x, seg_end_y)
        """
        # Extract offsets from path_data (these account for the edge connection point on the node border)
        sx = path_data.get('sx', 0) if path_data else 0
        sy = path_data.get('sy', 0) if path_data else 0
        tx = path_data.get('tx', 0) if path_data else 0
        ty = path_data.get('ty', 0) if path_data else 0
        
        # Actual path start/end points (with offsets applied to node centers)
        path_start = None
        path_end = None
        if source_center:
            path_start = (source_center[0] + sx, source_center[1] + sy)
        if target_center:
            path_end = (target_center[0] + tx, target_center[1] + ty)
        
        if not path_data or not path_data['points']:
            # No waypoints: segment 0 goes from path_start to path_end
            if path_start and path_end:
                return path_start[0], path_start[1], path_end[0], path_end[1]
            elif path_start:
                return path_start[0], path_start[1], path_start[0], path_start[1]
            else:
                return 0.0, 0.0, 0.0, 0.0
        
        points = path_data['points']
        
        if segment_index == 0:
            # Segment 0: from (source_center + offsets) to first waypoint
            # BUT: if node label overlaps this segment, use node label center instead
            segment_start = path_start
            if source_node_label_center is not None and path_start is not None:
                # Check if segment 0 is vertical or horizontal
                seg_end = points[0]
                dx = abs(seg_end[0] - path_start[0])
                dy = abs(seg_end[1] - path_start[1])
                
                # If segment is vertical (dx < 5 pixels tolerance)
                if dx < 5 and path_start[0] is not None:
                    # Check if label center is near the segment X coordinate
                    if abs(source_node_label_center[0] - path_start[0]) < 5:
                        # Label is on vertical segment, use its center
                        segment_start = source_node_label_center
                
                # If segment is horizontal (dy < 5 pixels tolerance)
                elif dy < 5 and path_start[1] is not None:
                    # Check if label center is near the segment Y coordinate
                    if abs(source_node_label_center[1] - path_start[1]) < 5:
                        # Label is on horizontal segment, use its center
                        segment_start = source_node_label_center
            
            if segment_start:
                return segment_start[0], segment_start[1], points[0][0], points[0][1]
            else:
                return 0.0, 0.0, points[0][0], points[0][1]
        
        elif segment_index < len(points):
            # Middle segments: from waypoint[segment_index-1] to waypoint[segment_index]
            return (points[segment_index - 1][0], points[segment_index - 1][1],
                   points[segment_index][0], points[segment_index][1])
        
        elif segment_index == len(points):
            # Last segment: from last waypoint to (target_center + offsets)
            if path_end:
                return points[-1][0], points[-1][1], path_end[0], path_end[1]
            else:
                return points[-1][0], points[-1][1], points[-1][0], points[-1][1]
        
        else:
            # Invalid segment index: default to source to target
            if source_center and target_center:
                return source_center[0], source_center[1], target_center[0], target_center[1]
            else:
                return 0.0, 0.0, 0.0, 0.0
    
    def _extract_edge_labels(self):
        """Extract edge label information from already parsed edges"""
        for edge in self.edges:
            if 'labels' in edge and edge['labels']:
                for label_attrs in edge['labels']:
                    edge_label_data = {
                        'edge_id': edge['id'],
                        'source': edge['source'],
                        'target': edge['target'],
                        'text': label_attrs.get('text', ''),
                        'x': label_attrs.get('x', 0),  # XML offsets perpendiculaires
                        'y': label_attrs.get('y', 0),
                        'width': label_attrs.get('width', 0),
                        'height': label_attrs.get('height', 0),
                        # Stocker les données pour le calcul en ÉTAPE 2
                        'path_data': label_attrs.get('path_data'),
                        'source_id': label_attrs.get('source_id'),
                        'target_id': label_attrs.get('target_id'),
                        'smart_edge_label_model_parameter': label_attrs.get('smart_edge_label_model_parameter'),
                    }
                    
                    self.edge_labels.append(edge_label_data)
                    
                    # Update bounds
                    half_width = label_attrs.get('width', 0) / 2
                    half_height = label_attrs.get('height', 0) / 2
                    # Note: bounds will be updated when we have final abs_x/abs_y
                    # but we don't know those yet until ÉTAPE 2
    
    def _update_bounds(self, x1, y1, x2, y2):
        """Update bounding box"""
        self.min_x = min(self.min_x, x1, x2)
        self.min_y = min(self.min_y, y1, y2)
        self.max_x = max(self.max_x, x1, x2)
        self.max_y = max(self.max_y, y1, y2)
    
    def _calculate_bounds(self):
        """Calculate final bounds with margin"""
        margin = 40
        self.min_x -= margin
        self.min_y -= margin
        self.max_x += margin
        self.max_y += margin
    
    def draw_to_image(self, output_file: str):
        """Draw to image"""
        width = int((self.max_x - self.min_x) * self.scale) + 100
        height = int((self.max_y - self.min_y) * self.scale) + 150
        
        print(f"Image dimensions: {width}x{height}")
        
        img = Image.new('RGB', (width, height), color=COLORS['bg'])
        draw = ImageDraw.Draw(img)
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 14)
            font_normal = ImageFont.truetype("arial.ttf", 10)
            font_small = ImageFont.truetype("arial.ttf", 9)
        except:
            font_title = ImageFont.load_default()
            font_normal = font_title
            font_small = font_title
        
        # Draw title
        draw.text((10, 10), f"GraphML Analysis: {self.graphml_file}", fill=COLORS['text'], font=font_title)
        draw.line([(10, 35), (width - 10, 35)], fill=COLORS['grid'], width=1)
        
        # Draw grid lines
        self._draw_grid(draw)
        
        # Draw groups
        for group in self.groups:
            self._draw_group(draw, group, font_small)
        
        # Draw edges
        for edge in self.edges:
            self._draw_edge_line(draw, edge)
        
        # Draw nodes
        for node in self.nodes:
            self._draw_node_rect(draw, node, font_normal)
        
        # Draw node labels
        for node in self.nodes:
            self._draw_node_label(draw, node, font_small)
        
        # Draw edge coordinates in foreground (after nodes so they're not hidden)
        self._draw_edge_coordinates(draw, font_small)
        
        # Draw all edge labels with SmartEdgeLabelModelParameter (or without)
        self._draw_translated_edge_labels(draw, font_small)
        
        img.save(output_file, 'JPEG', quality=95)
        print(f"* Image saved: {output_file}")
    
    def _transform(self, x: float, y: float) -> Tuple[int, int]:
        """Transform world coordinates to image coordinates"""
        img_x = int((x - self.min_x) * self.scale) + 50
        img_y = int((y - self.min_y) * self.scale) + 50
        return (img_x, img_y)
    
    def _draw_grid(self, draw: ImageDraw.ImageDraw):
        """Draw reference grid"""
        grid_step = 50
        for x in range(0, int((self.max_x - self.min_x) * self.scale) + 100, int(grid_step * self.scale)):
            draw.line([(x + 50, 45), (x + 50, 50)], fill=COLORS['grid'], width=1)
        for y in range(0, int((self.max_y - self.min_y) * self.scale) + 150, int(grid_step * self.scale)):
            draw.line([(45, y + 50), (50, y + 50)], fill=COLORS['grid'], width=1)
    
    def _draw_group(self, draw: ImageDraw.ImageDraw, group: Dict, font):
        """Draw a group rectangle"""
        x1, y1 = self._transform(group['x'], group['y'])
        x2, y2 = self._transform(group['x'] + group['width'], group['y'] + group['height'])
        
        # Draw dashed rectangle
        draw.rectangle([x1, y1, x2, y2], outline=COLORS['group'], width=2)
        
        # Draw label and coordinates
        draw.text((x1 + 5, y1 + 5), f"GROUP: {group['label']}", fill=COLORS['group'], font=font)
        draw.text((x1 + 5, y1 + 20), f"ID={group['id']}", fill=COLORS['group'], font=font)
        draw.text((x1 + 5, y1 + 35), f"X={group['x']:.1f} Y={group['y']:.1f}", fill=COLORS['group'], font=font)
        draw.text((x1 + 5, y1 + 50), f"W={group['width']:.1f} H={group['height']:.1f}", fill=COLORS['group'], font=font)
    
    def _draw_node_rect(self, draw: ImageDraw.ImageDraw, node: Dict, font):
        """Draw a node rectangle"""
        x1, y1 = self._transform(node['x'], node['y'])
        x2, y2 = self._transform(node['x'] + node['width'], node['y'] + node['height'])
        
        # Draw filled rectangle
        draw.rectangle([x1, y1, x2, y2], outline=COLORS['node'], fill=(200, 255, 200), width=2)
        
        # Draw label inside (centered)
        label_x = (x1 + x2) // 2 - 25
        label_y = (y1 + y2) // 2 - 20
        draw.text((label_x, label_y), node['label'], fill=COLORS['text'], font=font)
        
        # Draw ID above the rectangle with background
        id_text = f"ID: {node['id']}"
        bbox = draw.textbbox((x1, y1 - 25), id_text, font=font)
        draw.rectangle(bbox, fill=(200, 255, 200))
        draw.text((x1, y1 - 25), id_text, fill=COLORS['text'], font=font)
        
        # Draw coordinates below ID with background
        coords_text = f"X={node['x']:.1f} Y={node['y']:.1f}"
        bbox = draw.textbbox((x1, y1 - 12), coords_text, font=font)
        draw.rectangle(bbox, fill=(200, 255, 200))
        draw.text((x1, y1 - 12), coords_text, fill=COLORS['text'], font=font)
        
        # Draw dimensions below the rectangle with background
        dims_text = f"W={node['width']:.1f} H={node['height']:.1f}"
        bbox = draw.textbbox((x1, y2 + 3), dims_text, font=font)
        draw.rectangle(bbox, fill=(200, 255, 200))
        draw.text((x1, y2 + 3), dims_text, fill=COLORS['text'], font=font)
    
    def _draw_node_label(self, draw: ImageDraw.ImageDraw, node: Dict, font):
        """Draw a node's label in a rectangle with debug information"""
        # Get node label info using the new function
        label_info = self._find_node_label_info(node['id'])
        
        if label_info is None:
            # No label found
            return
        
        label_center = label_info['center']
        label_x_abs = label_info['x']
        label_y_abs = label_info['y']
        label_width = label_info['width']
        label_height = label_info['height']
        label_text = label_info['text']
        
        # Transform to image coordinates
        label_x, label_y = self._transform(label_center[0], label_center[1])
        img_x1, img_y1 = self._transform(label_x_abs, label_y_abs)
        img_x2 = img_x1 + label_width * self.scale
        img_y2 = img_y1 + label_height * self.scale
        
        # Draw rectangle for node label
        draw.rectangle([img_x1, img_y1, img_x2, img_y2], 
                      outline=(100, 150, 200), fill=(200, 230, 255), width=2)
        
        # Draw label text inside rectangle
        if label_text:
            draw.text((img_x1 + 5, img_y1 + 5), label_text, fill=(0, 0, 100), font=font)
        
        # Draw debug info: position and dimensions
        debug_text = f"X={label_x_abs:.1f} Y={label_y_abs:.1f}\nW={label_width:.1f} H={label_height:.1f}"
        draw.text((img_x2 + 5, img_y1), debug_text, fill=(100, 100, 200), font=font)
    
    def _draw_edge_line(self, draw: ImageDraw.ImageDraw, edge: Dict):
        """Draw an edge line"""
        if not edge['path'] or not edge['path']['points']:
            # Draw simple line
            source = self._find_node_center(edge['source'])
            target = self._find_node_center(edge['target'])
            if source and target:
                p1 = self._transform(source[0], source[1])
                p2 = self._transform(target[0], target[1])
                draw.line([p1, p2], fill=COLORS['edge'], width=2)
        else:
            # Draw polyline with proper path offset handling
            points = edge['path']['points']
            source = self._find_node_center(edge['source'])
            target = self._find_node_center(edge['target'])
            
            # Extract path offsets
            sx = edge['path'].get('sx', 0)
            sy = edge['path'].get('sy', 0)
            tx = edge['path'].get('tx', 0)
            ty = edge['path'].get('ty', 0)
            
            # CORRECT PATH TRACING:
            # 1. Start: source_center + (sx, sy)
            # 2. Waypoints: Point[0], Point[1], ...
            # 3. End: target_center + (tx, ty)
            
            coords = []
            
            # Add source with offset
            if source:
                source_with_offset = (source[0] + sx, source[1] + sy)
                coords.append(self._transform(source_with_offset[0], source_with_offset[1]))
            
            # Add waypoints
            for p in points:
                coords.append(self._transform(p[0], p[1]))
            
            # Add target with offset
            if target:
                target_with_offset = (target[0] + tx, target[1] + ty)
                coords.append(self._transform(target_with_offset[0], target_with_offset[1]))
            
            if len(coords) > 1:
                draw.line(coords, fill=COLORS['edge'], width=2)
            
            # Draw control points (waypoints, not the connection points)
            for point in points:
                px, py = self._transform(point[0], point[1])
                draw.ellipse([px-4, py-4, px+4, py+4], fill=COLORS['control_point'], outline=COLORS['control_point'])
    
    def _draw_edge_coordinates(self, draw: ImageDraw.ImageDraw, font):
        """Draw edge coordinates in foreground (after nodes)"""
        for edge in self.edges:
            if edge['path'] and edge['path']['points']:
                points = edge['path']['points']
                source = self._find_node_center(edge['source'])
                target = self._find_node_center(edge['target'])
                
                # Extract path offsets
                sx = edge['path'].get('sx', 0)
                sy = edge['path'].get('sy', 0)
                tx = edge['path'].get('tx', 0)
                ty = edge['path'].get('ty', 0)
                
                # Draw source and target coordinates with offsets applied
                if source:
                    source_with_offset = (source[0] + sx, source[1] + sy)
                    src_x, src_y = self._transform(source_with_offset[0], source_with_offset[1])
                    src_text = f"START: ({source_with_offset[0]:.1f},{source_with_offset[1]:.1f})"
                    # Draw semi-transparent background
                    bbox = draw.textbbox((src_x - 60, src_y - 35), src_text, font=font)
                    draw.rectangle(bbox, fill=(255, 255, 200, 200))
                    draw.text((src_x - 60, src_y - 35), src_text, fill=(0, 100, 200), font=font)
                
                if target:
                    target_with_offset = (target[0] + tx, target[1] + ty)
                    tgt_x, tgt_y = self._transform(target_with_offset[0], target_with_offset[1])
                    tgt_text = f"END: ({target_with_offset[0]:.1f},{target_with_offset[1]:.1f})"
                    # Draw semi-transparent background
                    bbox = draw.textbbox((tgt_x + 10, tgt_y + 25), tgt_text, font=font)
                    draw.rectangle(bbox, fill=(255, 255, 200, 200))
                    draw.text((tgt_x + 10, tgt_y + 25), tgt_text, fill=(0, 100, 200), font=font)
                
                # Draw control points coordinate labels with alternating positions
                point_idx = 0
                for point in points:
                    px, py = self._transform(point[0], point[1])
                    coord_text = f"P{point_idx}: ({point[0]:.1f},{point[1]:.1f})"
                    
                    # Alternate position above and below to avoid overlap
                    if point_idx % 2 == 0:
                        text_y = py - 25
                    else:
                        text_y = py + 15
                    
                    # Draw semi-transparent background
                    bbox = draw.textbbox((px + 8, text_y), coord_text, font=font)
                    draw.rectangle(bbox, fill=(255, 200, 200, 200))
                    draw.text((px + 8, text_y), coord_text, fill=COLORS['control_point'], font=font)
                    point_idx += 1
    
    def _draw_edge_label_box(self, draw: ImageDraw.ImageDraw, label: Dict, font):
        """Draw an edge label box"""
        x1, y1 = self._transform(label['x'], label['y'])
        x2, y2 = self._transform(label['x'] + label['width'], label['y'] + label['height'])
        
        # Draw rectangle
        draw.rectangle([x1, y1, x2, y2], outline=COLORS['label'], fill=(255, 220, 220), width=1)
        
        # Draw text
        text_x = x1 + 2
        text_y = y1 + 2
        draw.text((text_x, text_y), label['text'].strip(), fill=COLORS['label'], font=font)
        
        # Draw relative coordinates
        rel_coords_str = f"REL: X={label['x']:.1f} Y={label['y']:.1f}"
        draw.text((text_x, y2 + 3), rel_coords_str, fill=COLORS['label'], font=font)
        
        # Draw absolute coordinates (calculated from segment start)
        abs_coords_str = f"ABS: X={label['abs_x']:.1f} Y={label['abs_y']:.1f}"
        draw.text((text_x, y2 + 15), abs_coords_str, fill=(200, 0, 0), font=font)
        
        # Draw dimensions
        dims_str = f"W={label['width']:.1f} H={label['height']:.1f}"
        draw.text((text_x, y2 + 27), dims_str, fill=COLORS['label'], font=font)
        
        # Draw parameters if available
        if 'params' in label and label['params']:
            params_str = f"seg={label['params'].get('segment', -1)} ratio={label['params'].get('ratio', 0.5):.2f}"
            draw.text((text_x, y2 + 39), params_str, fill=COLORS['label'], font=font)
    
    def _draw_reference_rectangle(self, draw: ImageDraw.ImageDraw, font):
        """Draw reference rectangle using calculated absolute coordinates from EdgeLabel"""
        # Use the first edge label if available
        if not self.edge_labels:
            return
        
        label = self.edge_labels[0]
        
        # Use absolute coordinates (calculated from source center + relative offset)
        ref_x = label['abs_x']
        ref_y = label['abs_y']
        ref_width = label['width']
        ref_height = label['height']
        
        # Transform to image coordinates
        x1, y1 = self._transform(ref_x, ref_y)
        x2, y2 = self._transform(ref_x + ref_width, ref_y + ref_height)
        
        # Draw red rectangle
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), fill=(255, 200, 200), width=2)
        
        # Draw coordinates label
        coords_text = f"ABS: X={ref_x:.1f} Y={ref_y:.1f}"
        draw.text((x1 + 5, y1 - 15), coords_text, fill=(255, 0, 0), font=font)
        
        # Draw dimensions label
        dims_text = f"W={ref_width:.2f} H={ref_height:.2f}"
        draw.text((x1 + 5, y2 + 5), dims_text, fill=(255, 0, 0), font=font)
    
    def _get_segment_direction(self, edge: Dict, segment_index: int) -> Tuple[float, float]:
        """
        Calculate the direction of a segment in the edge path.
        Returns a normalized direction vector (dx, dy).
        
        Segment indexing:
        - Segment 0: from source center to first point (or to target if no points)
        - Segment 1: from first point to second point
        - Segment 2: from second point to third point
        - etc...
        - Segment len(points): from last point to target
        """
        if not edge['path'] or not edge['path']['points']:
            # For edges without explicit path, get direction from source to target
            source_center = self._find_node_center(edge['source'])
            target_center = self._find_node_center(edge['target'])
            if source_center and target_center:
                dx = target_center[0] - source_center[0]
                dy = target_center[1] - source_center[1]
            else:
                return (1, 0)  # Default to horizontal if centers not found
        else:
            points = edge['path']['points']
            source_center = self._find_node_center(edge['source'])
            target_center = self._find_node_center(edge['target'])
            
            if segment_index == 0:
                # First segment: from source to first point
                if source_center and len(points) > 0:
                    dx = points[0][0] - source_center[0]
                    dy = points[0][1] - source_center[1]
                else:
                    return (1, 0)
            elif segment_index < len(points):
                # Middle segments: from point[segment_index-1] to point[segment_index]
                dx = points[segment_index][0] - points[segment_index - 1][0]
                dy = points[segment_index][1] - points[segment_index - 1][1]
            elif segment_index == len(points):
                # Last segment: from last point to target
                if len(points) > 0 and target_center:
                    dx = target_center[0] - points[-1][0]
                    dy = target_center[1] - points[-1][1]
                else:
                    return (1, 0)
            else:
                return (1, 0)
        
        # Normalize the direction vector
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            return (dx / length, dy / length)
        else:
            return (1, 0)
    
    def _apply_label_translation(self, label: Dict, edge: Dict, segment_index: int, distance: float) -> Dict:
        """
        Apply a translation to the edge label in the direction of a specific segment.
        Returns a new label dict with translated coordinates.
        """
        # Get the direction of the segment
        direction_x, direction_y = self._get_segment_direction(edge, segment_index)
        
        # Calculate the translation
        translation_x = direction_x * distance
        translation_y = direction_y * distance
        
        # Create a new label with translated coordinates
        translated_label = label.copy()
        translated_label['abs_x'] = label['abs_x'] + translation_x
        translated_label['abs_y'] = label['abs_y'] + translation_y
        translated_label['translation_applied'] = True
        translated_label['translation_segment'] = segment_index
        translated_label['translation_distance'] = distance
        translated_label['translation_direction'] = (direction_x, direction_y)
        
        return translated_label
    
    def _calculate_label_position_on_segment(self, segment_index: int, ratio: float, 
                                               distance: float, label: Dict) -> Tuple[float, float]:
        """
        Calcule la position FINALE du label en appliquant le modèle SmartEdgeLabel "zone sûre".
        
        LOGIQUE:
        1. Identifier le segment concerné (segment_index)
        2. Récupérer les points de début et fin de ce segment
        3. Calculer les limites de la safe zone sur ce segment:
           - P0 = seg_start + distance × direction
           - P1 = seg_end - distance × direction
        4. Interpoler la position au ratio dans la safe zone
        5. La position finale est TOUJOURS sur le segment
        
        RÈGLE pour les offsets XML:
        - Si SmartEdgeLabelModelParameter: utiliser safe zone SANS offsets XML
        - Si pas SmartEdgeLabelModelParameter: utiliser offsets XML directement
        """
        # Récupérer les données de base
        source_id = label.get('source_id')
        target_id = label.get('target_id')
        path_data = label.get('path_data', {})
        
        source_center = self._find_node_center(source_id)
        target_center = self._find_node_center(target_id)
        
        text = label.get('text', '')
        has_smart_params = 'smart_edge_label_model_parameter' in label
        
        # Extraire le segment_index depuis SmartEdgeLabelModelParameter si présent
        if has_smart_params:
            smart_model = label.get('smart_edge_label_model_parameter', {})
            segment_index = int(smart_model.get('segment', segment_index))
        
        if not source_center or not target_center:
            # Fallback: utiliser les offsets XML simplement
            return (label.get('x', 0), label.get('y', 0))
        
        # Si pas de SmartEdgeLabelModelParameter, utiliser juste les offsets XML
        if not has_smart_params:
            xml_offset_x = float(label.get('x', 0))
            xml_offset_y = float(label.get('y', 0))
            if text == "sync":
                print(f"\n{'='*80}")
                print(f"Using simple XML offsets (no SmartEdgeLabelModelParameter)")
                print(f"XML offsets: x={xml_offset_x}, y={xml_offset_y}")
                print(f"FINAL POSITION: ({xml_offset_x}, {xml_offset_y})")
                print(f"{'='*80}\n")
            return (xml_offset_x, xml_offset_y)
        
        # Sinon, utiliser la formule safe zone sur le segment concerné
        
        # STEP 1: Récupérer les endpoints du segment concerné
        seg_start_x, seg_start_y, seg_end_x, seg_end_y = self._get_segment_endpoints(
            segment_index, source_center, target_center, path_data
        )
        
        if text == "sync":
            print(f"\n{'='*80}")
            print(f"DETAILED CALCULATION FOR LABEL: {text}")
            print(f"Segment index: {segment_index}")
            print(f"{'='*80}")
            print(f"Segment start: ({seg_start_x}, {seg_start_y})")
            print(f"Segment end: ({seg_end_x}, {seg_end_y})")
        
        if text == "tatatatatata":
            print(f"\n{'='*80}")
            print(f"DETAILED CALCULATION FOR LABEL: {text}")
            print(f"Segment index: {segment_index}")
            print(f"{'='*80}")
            print(f"Segment start: ({seg_start_x}, {seg_start_y})")
            print(f"Segment end: ({seg_end_x}, {seg_end_y})")
        
        # STEP 2: Calculer la direction normalisée du segment
        dx = seg_end_x - seg_start_x
        dy = seg_end_y - seg_start_y
        seg_length = math.sqrt(dx*dx + dy*dy)
        
        if text == "sync":
            print(f"Direction vector: dx={dx}, dy={dy}")
            print(f"Segment length: {seg_length}")
        
        if text == "tatatatatata":
            print(f"Direction vector: dx={dx}, dy={dy}")
            print(f"Segment length: {seg_length}")
        
        if seg_length == 0:
            if text == "sync":
                print(f"Zero-length segment, returning start point")
                print(f"{'='*80}\n")
            return (seg_start_x, seg_start_y)
        
        # Normaliser la direction
        norm_dx = dx / seg_length
        norm_dy = dy / seg_length
        
        if text == "sync":
            print(f"Normalized direction: norm_dx={norm_dx}, norm_dy={norm_dy}")
            print(f"Safe zone distance: {distance}")
        
        if text == "tatatatatata":
            print(f"Normalized direction: norm_dx={norm_dx}, norm_dy={norm_dy}")
            print(f"Safe zone distance: {distance}")
        
        # STEP 3: Calculer les limites de la safe zone sur le segment
        # Les waypoints sont déjà des points de safe zone, on ne recule pas de 30px
        # Les nœuds (source/target) nécessitent un recul de distance
        
        # Déterminer si start est un waypoint ou un nœud source
        waypoints = path_data.get('points', [])
        num_segments = len(waypoints) + 1 if waypoints else 1
        
        # segment 0 => start est nœud source (pas waypoint)
        # segment > 0 et segment < num_segments-1 => start et end sont waypoints
        # segment == num_segments-1 => end est nœud target (pas waypoint)
        
        start_is_waypoint = segment_index > 0
        end_is_waypoint = segment_index < (num_segments - 1)
        
        # P0 = seg_start + distance × direction (SAUF si start est un waypoint)
        if start_is_waypoint:
            p0_x = seg_start_x
            p0_y = seg_start_y
        else:
            p0_x = seg_start_x + distance * norm_dx
            p0_y = seg_start_y + distance * norm_dy
        
        # P1 = seg_end - distance × direction (SAUF si end est un waypoint)
        if end_is_waypoint:
            p1_x = seg_end_x
            p1_y = seg_end_y
        else:
            p1_x = seg_end_x - distance * norm_dx
            p1_y = seg_end_y - distance * norm_dy
        
        if text == "sync":
            print(f"Start is waypoint: {start_is_waypoint}, End is waypoint: {end_is_waypoint}")
            print(f"P0 (start of safe zone on segment): ({p0_x}, {p0_y})")
            print(f"P1 (end of safe zone on segment): ({p1_x}, {p1_y})")
        
        if text == "tatatatatata":
            print(f"Start is waypoint: {start_is_waypoint}, End is waypoint: {end_is_waypoint}")
            print(f"P0 (start of safe zone on segment): ({p0_x}, {p0_y})")
            print(f"P1 (end of safe zone on segment): ({p1_x}, {p1_y})")
        
        # STEP 4: Interpoler la position au ratio dans la safe zone
        label_point_x = p0_x + ratio * (p1_x - p0_x)
        label_point_y = p0_y + ratio * (p1_y - p0_y)
        
        if text == "sync":
            print(f"Ratio: {ratio}")
            print(f"Label point (on segment): ({label_point_x}, {label_point_y})")
            print(f"FINAL POSITION (safe zone on segment, NO XML offsets): ({label_point_x}, {label_point_y})")
            print(f"{'='*80}\n")
        
        if text == "tatatatatata":
            print(f"Ratio: {ratio}")
            print(f"Label point (on segment): ({label_point_x}, {label_point_y})")
            print(f"FINAL POSITION (safe zone on segment, NO XML offsets): ({label_point_x}, {label_point_y})")
            print(f"{'='*80}\n")
        
        return (label_point_x, label_point_y)
    
    def _apply_edge_label_adjustments(self, label: Dict, edge: Dict) -> Dict:
        """
        Apply adjustments to edge label coordinates based on SmartEdgeLabelModelParameter
        and segment orientation.
        
        Process:
        1. STEP 2a: Calculate orientation-based centering (center label on segment)
        2. STEP 2b: Calculate distance/ratio offset along segment
        3. STEP 2c: Calculate dimension-based compensation (center perpendicular to position)
        """
        # Create adjusted label with original coordinates as fallback
        adjusted_label = label.copy()
        
        # Get segment information
        if 'smart_edge_label_model_parameter' in label:
            smart_params = label['smart_edge_label_model_parameter']
            segment_index = int(smart_params.get('segment', 0))
            distance = float(smart_params.get('distance', 0.0))
            ratio = float(smart_params.get('ratio', 0.5))
            
            # SOLUTION: Utiliser le modèle zone sûre
            # Si distance > 0, utiliser la zone sûre
            if distance > 0:
                # Calculer la position du label avec le modèle zone sûre
                # Cette fonction retourne le point au bon endroit sur le segment
                # (avec sx/sy appliqués, mais SANS les offsets XML perpendiculaires)
                safe_zone_x, safe_zone_y = self._calculate_label_position_on_segment(
                    segment_index,
                    ratio,
                    distance,
                    label
                )
                
                # Ajouter les offsets du label XML (offsets perpendiculaires)
                # label['abs_x'] et label['abs_y'] contiennent les offsets du XML
                label_offset_x = label['abs_x']
                label_offset_y = label['abs_y']
                
                # Position finale = point sur zone sûre + offsets perpendiculaires du XML
                adjusted_label['adj_x'] = safe_zone_x + label_offset_x
                adjusted_label['adj_y'] = safe_zone_y + label_offset_y
                adjusted_label['adjustment_applied'] = True
                adjusted_label['adjustment_type'] = 'safe_zone_model'
                adjusted_label['safe_zone_position'] = (safe_zone_x, safe_zone_y)
                adjusted_label['label_offset'] = (label_offset_x, label_offset_y)
            else:
                # Pas de distance, utiliser les calculs d'ajustement existants
                # STEP 2a: Calculate orientation adjustment (centering)
                adj_x, adj_y = self._calculate_segment_orientation_adjustment(
                    segment_index,
                    label['width'],
                    label['height'],
                    edge
                )
                
                # STEP 2b: Calculate distance/ratio offset along segment
                # Apply ratio to distance: offset = distance * ratio
                segment_offset = distance * ratio
                
                # Get the direction of the segment to apply offset
                dist_adj_x, dist_adj_y = self._calculate_distance_ratio_adjustment(
                    segment_index,
                    segment_offset,
                    edge
                )
                
                # STEP 2c: Calculate dimension compensation (perpendicular centering)
                comp_x, comp_y = self._calculate_dimension_compensation_adjustment(
                    segment_index,
                    label['width'],
                    label['height'],
                    edge
                )
                
                # Combine all adjustments
                total_adj_x = adj_x + dist_adj_x + comp_x
                total_adj_y = adj_y + dist_adj_y + comp_y
                
                if adj_x != 0 or adj_y != 0 or dist_adj_x != 0 or dist_adj_y != 0 or comp_x != 0 or comp_y != 0:
                    # Apply combined adjustment
                    adjusted_label['adj_x'] = label['abs_x'] + total_adj_x
                    adjusted_label['adj_y'] = label['abs_y'] + total_adj_y
                    adjusted_label['adjustment_applied'] = True
                    adjusted_label['adjustment_type'] = 'segment_orientation'
                    adjusted_label['adjustment_values'] = (total_adj_x, total_adj_y)
                    adjusted_label['orientation_adjustment'] = (adj_x, adj_y)
                    adjusted_label['distance_ratio_adjustment'] = (dist_adj_x, dist_adj_y)
                    adjusted_label['dimension_compensation_adjustment'] = (comp_x, comp_y)
                else:
                    adjusted_label['adjustment_applied'] = False
        else:
            adjusted_label['adjustment_applied'] = False
        
        return adjusted_label
    
    def _get_label_box_coordinates(self, center_x: float, center_y: float, width: float, height: float):
        """
        Calculate label box coordinates from center point.
        
        Args:
            center_x, center_y: Center coordinates of the label
            width, height: Dimensions of the label
            
        Returns:
            Tuple of (x1, y1, x2, y2) for the label box
        """
        half_width = width / 2
        half_height = height / 2
        return (center_x - half_width, center_y - half_height, 
                center_x + half_width, center_y + half_height)
    
    def _calculate_segment_orientation_adjustment(self, segment_index: int, label_width: float, 
                                                  label_height: float, edge: Dict) -> Tuple[float, float]:
        """
        Calculate adjustment to label coordinates based on segment orientation.
        
        For a label to be properly centered on a segment:
        - Vertical segment (dx ≈ 0): adjust X by ±width/2
        - Horizontal segment (dy ≈ 0): adjust Y by ±height/2
        - Diagonal segment: adjust proportionally based on slope
        
        Args:
            segment_index: Index of the segment
            label_width: Width of the label
            label_height: Height of the label
            edge: Edge dictionary with path information
            
        Returns:
            Tuple of (adjustment_x, adjustment_y)
        """
        
        # Get segment endpoints using standard path (source -> first waypoint or target)
        # Do NOT pass source_node_label_center as it's for node labels, not edge labels
        seg_start_x, seg_start_y, seg_end_x, seg_end_y = self._get_segment_endpoints(
            segment_index, 
            self._find_node_center(edge['source']),
            self._find_node_center(edge['target']),
            edge['path'],
            None  # source_node_label_center is for node labels, not edge labels
        )
        
        # Calculate segment direction
        dx = seg_end_x - seg_start_x
        dy = seg_end_y - seg_start_y
        
        # Handle zero-length segment
        if dx == 0 and dy == 0:
            return (0, 0)

        # Calculate segment length
        seg_length = math.sqrt(dx*dx + dy*dy)
        
        # Determine segment orientation
        tolerance = 5.0  # pixels
        
        if abs(dx) < tolerance:
            # VERTICAL segment: adjust X by +width/2 (label center is at edge point, need to move right)
            adjustment_x = label_width / 2
            adjustment_y = 0
            return (adjustment_x, adjustment_y)
        
        elif abs(dy) < tolerance:
            # HORIZONTAL segment: adjust Y by +height/2
            adjustment_x = 0
            adjustment_y = label_height / 2
            return (adjustment_x, adjustment_y)
        
        else:
            # DIAGONAL segment: calculate slope and adjust proportionally
            slope = dy / dx
            
            # Normalize direction vector
            norm_dx = dx / seg_length
            norm_dy = dy / seg_length
            
            # Perpendicular vector (rotated 90 degrees counterclockwise)
            perp_dx = -norm_dy
            perp_dy = norm_dx
            
            # Adjust proportionally based on label dimensions and perpendicular direction
            adjustment_x = (label_width / 2) * perp_dx
            adjustment_y = (label_height / 2) * perp_dy
            
            return (adjustment_x, adjustment_y)
    
    def _calculate_distance_ratio_adjustment(self, segment_index: int, segment_offset: float, edge: Dict) -> Tuple[float, float]:
        """
        Calculate adjustment based on distance and ratio parameters from SmartEdgeLabelModelParameter.
        
        The offset is applied along the segment direction:
        - For segments, calculate the direction from start to end
        - Apply the offset in that direction
        
        Args:
            segment_index: Index of the segment
            segment_offset: Distance * ratio (the actual offset to apply)
            edge: Edge dictionary with path information
            
        Returns:
            Tuple of (adjustment_x, adjustment_y)
        """
        if segment_offset == 0:
            return (0, 0)
        
        # Get segment endpoints using standard path (source -> first waypoint or target)
        # Do NOT pass source_node_label_center as it's for node labels, not edge labels
        seg_start_x, seg_start_y, seg_end_x, seg_end_y = self._get_segment_endpoints(
            segment_index, 
            self._find_node_center(edge['source']),
            self._find_node_center(edge['target']),
            edge['path'],
            None  # source_node_label_center is for node labels, not edge labels
        )
        
        # Calculate segment direction
        dx = seg_end_x - seg_start_x
        dy = seg_end_y - seg_start_y
        
        # Handle zero-length segment
        if dx == 0 and dy == 0:
            return (0, 0)
        
        # Calculate segment length
        seg_length = math.sqrt(dx*dx + dy*dy)
        
        # Normalize direction vector
        norm_dx = dx / seg_length
        norm_dy = dy / seg_length
        
        # Apply offset along segment direction
        # The offset moves the label along the segment path
        adjustment_x = segment_offset * norm_dx
        adjustment_y = segment_offset * norm_dy
        
        return (adjustment_x, adjustment_y)
    
    def _calculate_dimension_compensation_adjustment(self, segment_index: int, label_width: float, 
                                                     label_height: float, edge: Dict) -> Tuple[float, float]:
        """
        Calculate compensation adjustment based on label dimensions.
        
        This centers the label perpendicular to its position along the segment:
        - For VERTICAL segments: apply -height/2 to Y
        - For HORIZONTAL segments: apply -width/2 to X
        - For DIAGONAL segments: apply proportionally
        
        Args:
            segment_index: Index of the segment
            label_width: Width of the label
            label_height: Height of the label
            edge: Edge dictionary with path information
            
        Returns:
            Tuple of (compensation_x, compensation_y)
        """
        # Get segment endpoints using standard path (source -> first waypoint or target)
        # Do NOT pass source_node_label_center as it's for node labels, not edge labels
        seg_start_x, seg_start_y, seg_end_x, seg_end_y = self._get_segment_endpoints(
            segment_index, 
            self._find_node_center(edge['source']),
            self._find_node_center(edge['target']),
            edge['path'],
            None  # source_node_label_center is for node labels, not edge labels
        )
        
        # Calculate segment direction
        dx = seg_end_x - seg_start_x
        dy = seg_end_y - seg_start_y
        
        # Handle zero-length segment
        if dx == 0 and dy == 0:
            return (0, 0)
        
        # Calculate segment length
        seg_length = math.sqrt(dx*dx + dy*dy)
        
        # Determine segment orientation
        tolerance = 5.0  # pixels
        
        if abs(dx) < tolerance:
            # VERTICAL segment: NO compensation in Y (label stays on the segment Y position)
            # Only center perpendicular to segment (in X), which is already done by STEP 2a
            compensation_x = 0
            compensation_y = 0
            return (compensation_x, compensation_y)
        
        elif abs(dy) < tolerance:
            # HORIZONTAL segment: NO compensation in X (label stays on the segment X position)
            # Only center perpendicular to segment, which is already done by STEP 2a
            compensation_x = 0
            compensation_y = 0
            return (compensation_x, compensation_y)
        
        else:
            # DIAGONAL segment: apply proportionally
            # Normalize direction vector
            norm_dx = dx / seg_length
            norm_dy = dy / seg_length
            
            # Apply compensation proportionally along both dimensions
            compensation_x = -(label_width / 2) * abs(norm_dx)
            compensation_y = -(label_height / 2) * abs(norm_dy)
            
            return (compensation_x, compensation_y)
    
    def _draw_translated_edge_labels(self, draw: ImageDraw.ImageDraw, font):
        """
        Dessine les labels des arêtes en appliquant le modèle SmartEdgeLabel.
        
        ALGORITHME:
        1. Pour chaque label d'arête
        2. Récupérer distance et ratio du modèle SmartEdgeLabel
        3. Calculer position = _calculate_label_position_on_segment()
           (INCLUT: zone sûre + offsets path + offsets XML)
        4. Transformer en coordonnées image
        5. Dessiner le rectangle du label avec ses dimensions réelles
        6. Afficher les coordonnées et dimensions
        """
        if not self.edge_labels:
            return
        
        for label in self.edge_labels:
            # Récupérer les paramètres du modèle SmartEdgeLabel
            smart_model = label.get('smart_edge_label_model_parameter', {})
            
            # Convertir les strings XML en floats/ints
            try:
                distance = float(smart_model.get('distance', '30.0'))
                ratio = float(smart_model.get('ratio', '0.5'))
                segment_index = int(smart_model.get('segment', 0))
            except (ValueError, TypeError):
                distance = 30.0
                ratio = 0.5
                segment_index = 0
            
            # Récupérer le texte (avant DEBUG)
            text = label.get('text', '').strip()
            if not text:
                continue
            
            # Calculer la position FINALE (zone sûre + offsets appliqués)
            final_x, final_y = self._calculate_label_position_on_segment(
                segment_index=segment_index,
                ratio=ratio,
                distance=distance,
                label=label
            )
            
            # Transformer au système de coordonnées de l'image (centre du label)
            img_x, img_y = self._transform(final_x, final_y)
            
            # Récupérer les dimensions du label
            label_width = float(label.get('width', 50))
            label_height = float(label.get('height', 20))
            
            # Transformer les dimensions en pixels image
            scaled_width = label_width * self.scale
            scaled_height = label_height * self.scale
            
            # Calculer le rectangle centré au point final_x, final_y
            label_x1 = img_x - scaled_width / 2
            label_y1 = img_y - scaled_height / 2
            label_x2 = img_x + scaled_width / 2
            label_y2 = img_y + scaled_height / 2
            
            # Dessiner le rectangle du label
            draw.rectangle([label_x1, label_y1, label_x2, label_y2], 
                          outline=COLORS['text'], fill=(220, 240, 255), width=2)
            
            # Calculer l'ancrage pour centrer le texte dans le rectangle
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Centrer le texte dans le rectangle
            text_x = int(img_x - text_width / 2)
            text_y = int(img_y - text_height / 2)
            
            # Dessiner le texte
            draw.text((text_x, text_y), text, font=font, fill=COLORS['text'])
            
            # Afficher les coordonnées finales du label
            coords_text = f"X={final_x:.1f} Y={final_y:.1f}"
            coords_bbox = draw.textbbox((0, 0), coords_text, font=font)
            coords_width = coords_bbox[2] - coords_bbox[0]
            coords_height = coords_bbox[3] - coords_bbox[1]
            
            # Placer les coordonnées au-dessus du label
            coords_x = int(label_x1)
            coords_y = int(label_y1 - coords_height - 8)
            
            # Fond blanc pour les coordonnées
            coords_box_x1 = coords_x - 2
            coords_box_y1 = coords_y - 2
            coords_box_x2 = coords_x + coords_width + 2
            coords_box_y2 = coords_y + coords_height + 2
            draw.rectangle([coords_box_x1, coords_box_y1, coords_box_x2, coords_box_y2], 
                          fill=(255, 255, 200), outline=(150, 150, 0))
            draw.text((coords_x, coords_y), coords_text, font=font, fill=(100, 100, 0))
            
            # Afficher les dimensions du label
            dims_text = f"W={label_width:.1f} H={label_height:.1f}"
            dims_bbox = draw.textbbox((0, 0), dims_text, font=font)
            dims_width = dims_bbox[2] - dims_bbox[0]
            dims_height = dims_bbox[3] - dims_bbox[1]
            
            # Placer les dimensions en bas du label
            dims_x = int(label_x1)
            dims_y = int(label_y2 + 3)
            
            # Fond blanc pour les dimensions
            dims_box_x1 = dims_x - 2
            dims_box_y1 = dims_y - 2
            dims_box_x2 = dims_x + dims_width + 2
            dims_box_y2 = dims_y + dims_height + 2
            draw.rectangle([dims_box_x1, dims_box_y1, dims_box_x2, dims_box_y2], 
                          fill=(255, 255, 200), outline=(150, 150, 0))
            draw.text((dims_x, dims_y), dims_text, font=font, fill=(100, 100, 0))
        
        print("\n" + "="*80)
    
    def _find_node_center(self, node_id: str) -> Tuple[float, float]:
        """Find node center"""
        for node in self.nodes:
            if node['id'] == node_id:
                return (node['x'] + node['width']/2, node['y'] + node['height']/2)
        for group in self.groups:
            if group['id'] == node_id:
                return (group['x'] + group['width']/2, group['y'] + group['height']/2)
        return None
    
    def _find_node_label_center(self, node_id: str) -> Tuple[float, float]:
        """
        Find the center of a node's label in absolute coordinates.
        
        The node label is positioned relative to the SVGNode/ShapeNode/GroupNode geometry,
        so we need to:
        1. Find the node and its geometry (x, y)
        2. Get the node label relative position and size from the XML
        3. Calculate the absolute center: (node_x + label_x + label_width/2, node_y + label_y + label_height/2)
        
        Returns:
            Tuple of (label_center_x, label_center_y) in absolute coordinates, or None if no label found
        """
        # Find the node in XML
        for node_elem in self.root.findall('.//graphml:node', NAMESPACES):
            if node_elem.get('id') != node_id:
                continue
            
            # Try to find the node label in SVGNode, ShapeNode, or GroupNode
            label_elem = None
            geom_elem = None
            
            # Check ShapeNode
            shape_node = node_elem.find('.//y:ShapeNode', NAMESPACES)
            if shape_node is not None:
                label_elem = self._get_best_node_label_element(shape_node)
                geom_elem = shape_node.find('.//y:Geometry', NAMESPACES)
            
            # Check SVGNode
            if label_elem is None:
                svg_node = node_elem.find('.//y:SVGNode', NAMESPACES)
                if svg_node is not None:
                    label_elem = self._get_best_node_label_element(svg_node)
                    geom_elem = svg_node.find('.//y:Geometry', NAMESPACES)
            
            # Check GroupNode
            if label_elem is None:
                group_node = node_elem.find('.//y:ProxyAutoBoundsNode/y:Realizers/y:GroupNode[1]', NAMESPACES)
                if group_node is not None:
                    label_elem = self._get_best_node_label_element(group_node)
                    geom_elem = group_node.find('.//y:Geometry', NAMESPACES)
            
            if label_elem is not None and geom_elem is not None:
                # Extract label position and size (relative to the node's geometry)
                label_x = float(label_elem.get('x', 0))
                label_y = float(label_elem.get('y', 0))
                label_width = float(label_elem.get('width', 0))
                label_height = float(label_elem.get('height', 0))
                
                # Extract node geometry position
                node_x = float(geom_elem.get('x', 0))
                node_y = float(geom_elem.get('y', 0))
                
                # Calculate absolute label center by adding node position to relative label position
                abs_label_center_x = node_x + label_x + label_width / 2
                abs_label_center_y = node_y + label_y + label_height / 2
                return (abs_label_center_x, abs_label_center_y)
        
        return None
    
    def _find_node_label_info(self, node_id: str) -> Dict:
        """
        Find complete node label information including position, size, and text.
        
        Returns:
            Dict with keys: 'center', 'x', 'y', 'width', 'height', 'text', or None if no label found
        """
        # Find the node in XML
        for node_elem in self.root.findall('.//graphml:node', NAMESPACES):
            if node_elem.get('id') != node_id:
                continue
            
            # Try to find the node label in SVGNode, ShapeNode, or GroupNode
            label_elem = None
            geom_elem = None
            
            # Check ShapeNode
            shape_node = node_elem.find('.//y:ShapeNode', NAMESPACES)
            if shape_node is not None:
                label_elem = self._get_best_node_label_element(shape_node)
                geom_elem = shape_node.find('.//y:Geometry', NAMESPACES)
            
            # Check SVGNode
            if label_elem is None:
                svg_node = node_elem.find('.//y:SVGNode', NAMESPACES)
                if svg_node is not None:
                    label_elem = self._get_best_node_label_element(svg_node)
                    geom_elem = svg_node.find('.//y:Geometry', NAMESPACES)
            
            # Check GroupNode
            if label_elem is None:
                group_node = node_elem.find('.//y:ProxyAutoBoundsNode/y:Realizers/y:GroupNode[1]', NAMESPACES)
                if group_node is not None:
                    label_elem = self._get_best_node_label_element(group_node)
                    geom_elem = group_node.find('.//y:Geometry', NAMESPACES)
            
            if label_elem is not None and geom_elem is not None:
                # Extract label position and size (relative to the node's geometry)
                label_x = float(label_elem.get('x', 0))
                label_y = float(label_elem.get('y', 0))
                label_width = float(label_elem.get('width', 0))
                label_height = float(label_elem.get('height', 0))
                label_text = label_elem.text or ''
                
                # Extract node geometry position
                node_x = float(geom_elem.get('x', 0))
                node_y = float(geom_elem.get('y', 0))
                
                # Calculate absolute label center by adding node position to relative label position
                abs_label_center_x = node_x + label_x + label_width / 2
                abs_label_center_y = node_y + label_y + label_height / 2
                
                return {
                    'center': (abs_label_center_x, abs_label_center_y),
                    'x': node_x + label_x,
                    'y': node_y + label_y,
                    'width': label_width,
                    'height': label_height,
                    'text': label_text
                }
        
        return None
    
    def print_edge_label_parameters(self):
        """Print all edge label parameters for debugging"""
        print("\n" + "="*80)
        print("EDGE LABEL PARAMETERS ANALYSIS")
        print("="*80)
        for i, label in enumerate(self.edge_labels):
            print(f"\nEdge Label #{i+1}:")
            print(f"  Edge ID: {label.get('edge_id')}")
            print(f"  Source: {label.get('source')}")
            print(f"  Target: {label.get('target')}")
            print(f"  Text: {label.get('text')}")
            print(f"  Position (relative): X={label.get('x')}, Y={label.get('y')}")
            print(f"  Position (absolute): X={label.get('abs_x')}, Y={label.get('abs_y')}")
            print(f"  Dimensions: W={label.get('width')}, H={label.get('height')}")
            
            # Show reference point used
            ref_point = label.get('reference_point_used')
            if ref_point:
                print(f"  Reference Point: X={ref_point[0]:.2f}, Y={ref_point[1]:.2f}")
            
            source_label_center = label.get('source_node_label_center')
            if source_label_center:
                print(f"  Source Node Label Center: X={source_label_center[0]:.2f}, Y={source_label_center[1]:.2f}")
            
            if 'model_parameter' in label:
                print(f"  y:ModelParameter:")
                for key, value in label['model_parameter'].items():
                    print(f"    {key}: {value}")
            
            if 'smart_edge_label_model_parameter' in label:
                print(f"  y:SmartEdgeLabelModelParameter:")
                for key, value in label['smart_edge_label_model_parameter'].items():
                    print(f"    {key}: {value}")
        print("\n" + "="*80)

# Test: Verify convert works
if __name__ == '__main__':

    visualizer = ImprovedGraphMLVisualizer('./graphml/simple1.graphml', scale=2.5)
    visualizer.parse()
    visualizer.print_edge_label_parameters()
    visualizer.draw_to_image('./target/simple1.jpg')

    visualizer = ImprovedGraphMLVisualizer('./graphml/simple2.graphml', scale=2.5)
    visualizer.parse()
    visualizer.print_edge_label_parameters()
    visualizer.draw_to_image('./target/simple2.jpg')

    visualizer = ImprovedGraphMLVisualizer('./graphml/simple3.graphml', scale=2.5)
    visualizer.parse()
    visualizer.print_edge_label_parameters()
    visualizer.draw_to_image('./target/simple3.jpg')