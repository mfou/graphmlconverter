#!/usr/bin/env python3
"""
Transform yEd GraphML to Mermaid diagram format (Markdown).

This script converts GraphML files exported from yEd to Markdown documents
containing embedded Mermaid diagram syntax. It supports:
- Node visualization with labels
- Edge connections with optional labels
- Group/subgraph organization
- Different diagram directions (TD, LR, BT, RL)
- Markdown formatting with diagram statistics

Usage:
    python graphml2mermaid.py <input.graphml> <output.md> [direction]

Examples:
    python graphml2mermaid.py ./graphml/simple2.graphml ./target/simple2.md
    python graphml2mermaid.py ./graphml/simple2.graphml ./target/simple2.md LR
    python graphml2mermaid.py ./graphml/simple2.graphml ./target/simple2.md BT

Diagram Directions:
    TD - Top to Down (default)
    LR - Left to Right
    BT - Bottom to Top
    RL - Right to Left

Output Format:
    Generates a Markdown (.md) file with:
    - Diagram title and metadata
    - Embedded ```mermaid code block
    - Node, group, and edge statistics

Dependencies:
    - graphmlcore.py: Core GraphML parsing utilities
"""

import sys
import os
from typing import Dict, List, Any, Tuple
import re

# Import core functions and types from graphmlcore
from graphmlcore import parse_graphml


class GraphMLToMermaid:
    """Convert GraphML to Mermaid diagram format."""
    
    def __init__(self, graphml_file: str, direction: str = 'TD'):
        """
        Initialize the converter.
        
        Args:
            graphml_file: Path to the GraphML file
            direction: Mermaid diagram direction (TD, LR, BT, RL)
        """
        self.graphml_file = graphml_file
        self.direction = direction
        self.data = None
        self.nodes = []
        self.edges = []
        self.groups = []
        self.node_map = {}  # Map node_id -> node_label for quick lookup
        self.group_map = {}  # Map group_id -> group_label
        self.node_styles = {}  # Map node_id -> style properties
        self.group_styles = {}  # Map group_id -> style properties
        self.edge_styles = {}  # Map edge_id -> style properties
        self.style_classes = {}  # Store classDef definitions
        
    def parse(self):
        """Parse the GraphML file and extract data and styles."""
        self.data = parse_graphml(self.graphml_file)
        self.nodes = self.data.get('nodes', [])
        self.edges = self.data.get('edges', [])
        self.groups = self.data.get('groups', [])
        
        # Build lookup maps
        for node in self.nodes:
            label = node.get('label', node['id'])
            # Handle label as dict or string
            if isinstance(label, dict):
                label = label.get('text', node['id'])
            self.node_map[node['id']] = label
        
        for group in self.groups:
            label = group.get('label', group['id'])
            # Handle label as dict or string
            if isinstance(label, dict):
                label = label.get('text', group['id'])
            self.group_map[group['id']] = label
        
        # Extract style properties from nodes, groups, and edges
        self._extract_styles()
    
    def _sanitize_id(self, node_id: str) -> str:
        """
        Sanitize node ID for Mermaid compatibility.
        
        Mermaid requires:
        - No special characters except underscore and hyphen
        - No spaces
        - No leading numbers
        """
        # Replace special characters with underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', node_id)
        # Remove leading numbers
        sanitized = re.sub(r'^([0-9]+)', r'n\1', sanitized)
        # Avoid reserved keywords
        reserved = {'graph', 'digraph', 'subgraph', 'end', 'node', 'edge'}
        if sanitized.lower() in reserved:
            sanitized = 'node_' + sanitized
        return sanitized
    
    def _sanitize_label(self, label: str) -> str:
        """
        Sanitize label for Mermaid display.
        Remove line breaks and excessive whitespace.
        """
        label = label.strip()
        label = re.sub(r'\s+', ' ', label)  # Replace multiple spaces with single
        label = re.sub(r'\n', ' ', label)   # Replace newlines with spaces
        return label
    
    def _wrap_label(self, label: str, wrap_char: str = '"') -> str:
        """
        Wrap label with quotes if needed.
        Use double quotes for labels with special characters.
        Mermaid special characters that require quoting: [ ] ( ) { } < > | : # ; 
        """
        label = self._sanitize_label(label)
        
        # Check if label needs wrapping
        # Always wrap to be safe and ensure proper escaping
        return f'{wrap_char}{label}{wrap_char}'
    
    def _get_node_display(self, node_id: str, label: str) -> str:
        """
        Get the Mermaid node display syntax.
        
        Format: id["label"] or id[label]
        """
        # Handle label as dict or string
        if isinstance(label, dict):
            label = label.get('text', node_id)
        elif not isinstance(label, str):
            label = str(label)
        
        sanitized_id = self._sanitize_id(node_id)
        wrapped_label = self._wrap_label(label)
        # wrapped_label already has quotes, so don't add them again
        return f'{sanitized_id}[{wrapped_label}]'
    
    def _extract_styles(self):
        """Extract style properties from nodes, groups, and edges."""
        # Extract node styles
        for node in self.nodes:
            node_id = node.get('id')
            styles = {}
            
            # Extract fill color
            if 'fill' in node:
                fill = node['fill']
                if isinstance(fill, dict):
                    color = fill.get('color', '#ffffff')
                else:
                    color = fill
                styles['fill'] = color
            
            # Extract stroke/line color and width
            if 'line_color' in node:
                styles['stroke'] = node['line_color']
            if 'line_width' in node:
                width = node['line_width']
                styles['stroke-width'] = f'{width}px'
            
            # Extract font properties
            if 'font_size' in node:
                styles['font-size'] = f'{node["font_size"]}px'
            if 'text_color' in node:
                styles['color'] = node['text_color']
            
            self.node_styles[node_id] = styles
        
        # Extract group styles
        for group in self.groups:
            group_id = group.get('id')
            styles = {}
            
            # Extract fill color with transparency support
            if 'fill' in group:
                fill = group['fill']
                if isinstance(fill, dict):
                    # Try to get color with alpha channel
                    color = fill.get('color', '#fafafa')
                    # Keep color as-is (may include alpha like #caecff80)
                else:
                    color = fill
                styles['fill'] = color
            else:
                # Default group fill with transparency
                styles['fill'] = '#caecff80'
            
            # Extract stroke/line color and width
            if 'line_color' in group:
                styles['stroke'] = group['line_color']
            else:
                styles['stroke'] = '#ccc'
                
            if 'line_width' in group:
                width = group['line_width']
                styles['stroke-width'] = f'{width}px'
            else:
                styles['stroke-width'] = '1px'
            
            # Add stroke-dasharray for group visual distinction
            styles['stroke-dasharray'] = '5,5'
            
            self.group_styles[group_id] = styles
        
        # Extract edge styles (each edge gets individual styling)
        for edge_index, edge in enumerate(self.edges):
            edge_id = edge.get('id')
            styles = {
                'index': edge_index,  # Store the edge index for linkStyle
            }
            
            # Extract line color
            if 'line_color' in edge:
                styles['stroke'] = edge['line_color']
            else:
                styles['stroke'] = '#000000'
            
            # Extract line width
            if 'line_width' in edge:
                width = edge['line_width']
                styles['stroke-width'] = f'{width}px'
            else:
                styles['stroke-width'] = '1px'
            
            # Extract line style (solid, dashed, dotted)
            if 'line_style' in edge:
                line_style = edge['line_style']
                if line_style == 'dashed':
                    styles['stroke-dasharray'] = '5,5'
                elif line_style == 'dotted':
                    styles['stroke-dasharray'] = '2,2'
            
            self.edge_styles[edge_id] = styles
    
    def _generate_class_definitions(self) -> List[str]:
        """Generate classDef and class assignment lines for Mermaid."""
        lines = []
        
        # Generate classDef for nodes with default Mermaid style
        node_style = self._merge_styles(self.node_styles, default_fill='#99ccff', default_stroke='#3366ff')
        if node_style:
            lines.append(f'    classDef node {node_style}')
        
        # Generate classDef for groups
        group_style = self._merge_styles(self.group_styles, default_fill='#fafafa')
        if group_style:
            lines.append(f'    classDef groupnode {group_style}')
        
        # Generate classDef for edges
        edge_style = self._merge_styles(self.edge_styles, default_fill='#ffffff')
        if edge_style:
            lines.append(f'    classDef edge {edge_style}')
        
        return lines
    
    def _merge_styles(self, style_dict: Dict[str, Dict[str, str]], default_fill: str = '#ffffff', default_stroke: str = '#ccc') -> str:
        """
        Merge multiple style properties into a single classDef string.
        Averages colors if multiple styles exist.
        
        Args:
            style_dict: Dict mapping id -> {property: value}
            default_fill: Default fill color if none specified
            default_stroke: Default stroke color if none specified
        
        Returns:
            Mermaid classDef style string
        """
        if not style_dict:
            return f'fill:{default_fill},stroke:{default_stroke},stroke-width:1px'
        
        # Collect all properties
        all_properties = {}
        for style_props in style_dict.values():
            for prop, value in style_props.items():
                if prop not in all_properties:
                    all_properties[prop] = []
                all_properties[prop].append(value)
        
        # Build merged style string with first value of each property
        style_parts = []
        
        if 'fill' in all_properties:
            style_parts.append(f"fill:{all_properties['fill'][0]}")
        else:
            style_parts.append(f"fill:{default_fill}")
        
        if 'stroke' in all_properties:
            style_parts.append(f"stroke:{all_properties['stroke'][0]}")
        else:
            style_parts.append(f"stroke:{default_stroke}")
        
        if 'stroke-width' in all_properties:
            style_parts.append(f"stroke-width:{all_properties['stroke-width'][0]}")
        else:
            style_parts.append("stroke-width:1px")
        
        if 'stroke-dasharray' in all_properties:
            style_parts.append(f"stroke-dasharray:{all_properties['stroke-dasharray'][0]}")
        
        if 'font-size' in all_properties:
            style_parts.append(f"font-size:{all_properties['font-size'][0]}")
        
        if 'color' in all_properties:
            style_parts.append(f"color:{all_properties['color'][0]}")
        
        return ','.join(style_parts)
    
    def _generate_link_styles(self) -> List[str]:
        """
        Generate linkStyle lines for individual edge styling.
        
        Mermaid linkStyle applies style to edges by index.
        Format: linkStyle 0 stroke:#0000ff,stroke-width:2px
        
        Returns:
            List of linkStyle lines
        """
        lines = []
        
        for edge_id, styles in self.edge_styles.items():
            if 'index' in styles:
                edge_index = styles['index']
                
                # Build style string for this edge
                style_parts = []
                
                if 'stroke' in styles:
                    style_parts.append(f"stroke:{styles['stroke']}")
                
                if 'stroke-width' in styles:
                    style_parts.append(f"stroke-width:{styles['stroke-width']}")
                
                if 'stroke-dasharray' in styles:
                    style_parts.append(f"stroke-dasharray:{styles['stroke-dasharray']}")
                
                if style_parts:
                    style_str = ','.join(style_parts)
                    lines.append(f'    linkStyle {edge_index} {style_str}')
        
        return lines
    
    def generate_mermaid_code(self) -> str:
        """
        Generate Mermaid diagram code (without markdown wrapper).
        
        Returns:
            String containing Mermaid diagram code
        """
        lines = []
        
        # Start diagram
        lines.append(f'graph {self.direction}')
        lines.append('')
        
        # Group nodes by their parent group (infer from ID)
        grouped_nodes = {}
        ungrouped_nodes = []
        
        # Build a set of group IDs for quick lookup
        group_ids = {g['id'] for g in self.groups}
        
        for node in self.nodes:
            node_id = node['id']
            parent_id = None
            
            # Try to extract parent_id from node ID (e.g., "n0::n0" -> parent is "n0")
            if '::' in node_id:
                potential_parent = node_id.split('::')[0]
                if potential_parent in group_ids:
                    parent_id = potential_parent
            
            # Explicit parent_id if available
            if not parent_id and 'parent_id' in node:
                parent_id = node['parent_id']
            
            if parent_id:
                if parent_id not in grouped_nodes:
                    grouped_nodes[parent_id] = []
                grouped_nodes[parent_id].append(node)
            else:
                ungrouped_nodes.append(node)
        
        # Draw ungrouped nodes
        if ungrouped_nodes:
            for node in ungrouped_nodes:
                label = node.get('label', node['id'])
                if isinstance(label, dict):
                    label = label.get('text', node['id'])
                node_display = self._get_node_display(node['id'], label)
                lines.append(f'    {node_display}')
            lines.append('')
        
        # Draw grouped nodes with subgraphs
        for group in self.groups:
            group_id = group['id']
            sanitized_group_id = self._sanitize_id(group_id)
            group_label = group.get('label', group_id)
            if isinstance(group_label, dict):
                group_label = group_label.get('text', group_id)
            group_label = self._sanitize_label(group_label)
            wrapped_group_label = self._wrap_label(group_label)
            
            lines.append(f'    subgraph {sanitized_group_id}[{wrapped_group_label}]')
            
            if group_id in grouped_nodes:
                for node in grouped_nodes[group_id]:
                    label = node.get('label', node['id'])
                    if isinstance(label, dict):
                        label = label.get('text', node['id'])
                    node_display = self._get_node_display(node['id'], label)
                    lines.append(f'        {node_display}')
            
            lines.append(f'    end')
            lines.append('')
        
        # Draw edges with optional labels
        if self.edges:
            lines.append('    %% Edges')
            for edge in self.edges:
                source_id = self._sanitize_id(edge.get('source', ''))
                target_id = self._sanitize_id(edge.get('target', ''))
                
                # Get edge labels
                edge_labels = edge.get('labels', [])
                
                if edge_labels:
                    # Edge with label
                    label_data = edge_labels[0]
                    label_text = label_data.get('text', '').strip() if isinstance(label_data, dict) else str(label_data).strip()
                    if label_text:
                        wrapped_label = self._wrap_label(label_text)
                        lines.append(f'    {source_id} -->|{wrapped_label}| {target_id}')
                    else:
                        lines.append(f'    {source_id} --> {target_id}')
                else:
                    # Edge without label
                    lines.append(f'    {source_id} --> {target_id}')
        
        lines.append('')
        
        # Add link styles for individual edge styling
        link_styles = self._generate_link_styles()
        if link_styles:
            lines.append('    %% Link styles (per-edge)')
            lines.extend(link_styles)
            lines.append('')
        
        # Add class definitions (classDef)
        class_defs = self._generate_class_definitions()
        if class_defs:
            lines.append('    %% Class definitions')
            lines.extend(class_defs)
            lines.append('')
        
        # Add class assignments for nodes and groups
        if self.node_styles or self.group_styles:
            lines.append('    %% Class assignments')
            
            # Assign node class to all nodes
            node_ids = [self._sanitize_id(node['id']) for node in self.nodes]
            if node_ids:
                lines.append(f'    class {",".join(node_ids)} node')
            
            # Assign groupnode class to all groups
            group_ids = [self._sanitize_id(group['id']) for group in self.groups]
            if group_ids:
                lines.append(f'    class {",".join(group_ids)} groupnode')
        
        return '\n'.join(lines)
    
    def generate_mermaid(self) -> str:
        """
        Generate complete Markdown document with embedded Mermaid diagram.
        
        Returns:
            String containing Markdown with wrapped Mermaid code
        """
        # Get the base GraphML filename for the title
        base_name = os.path.splitext(os.path.basename(self.graphml_file))[0]
        
        # Generate the Mermaid code
        mermaid_code = self.generate_mermaid_code()
        
        # Build Markdown document
        lines = []
        lines.append(f'# {base_name}')
        lines.append('')
        lines.append(f'**Diagram Type:** Mermaid ({self.direction})')
        lines.append(f'**Nodes:** {len(self.nodes)} | **Groups:** {len(self.groups)} | **Edges:** {len(self.edges)}')
        lines.append('')
        lines.append('```mermaid')
        lines.append(mermaid_code)
        lines.append('```')
        
        return '\n'.join(lines)
    
    def save_to_file(self, output_file: str):
        """
        Generate Markdown document with embedded Mermaid diagram and save to file.
        
        Args:
            output_file: Path to output .md file
        """
        # Ensure .md extension
        if not output_file.endswith('.md'):
            output_file = output_file.replace('.mermaid', '.md')
            if not output_file.endswith('.md'):
                output_file = os.path.splitext(output_file)[0] + '.md'
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        # Generate and write
        markdown_content = self.generate_mermaid()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"[OK] Markdown diagram saved: {output_file}")
        print(f"  - Nodes: {len(self.nodes)}")
        print(f"  - Groups: {len(self.groups)}")
        print(f"  - Edges: {len(self.edges)}")


def convert(input_path: str, output_path: str, direction: str = 'TD') -> str:
    """
    Convert GraphML to Markdown with embedded Mermaid diagram.
    
    Args:
        input_path: Path to GraphML file
        output_path: Path to output Markdown file
        direction: Diagram direction (TD, LR, BT, RL)
    
    Returns:
        Path to the generated file
    """
    converter = GraphMLToMermaid(input_path, direction=direction)
    converter.parse()
    converter.save_to_file(output_path)
    return output_path


# Test: Verify convert works
if __name__ == '__main__':
    direction = 'TD'  # Top-Down by default

    input_file = './graphml/simple.graphml'
    output_file = './target/simple.md'
    convert(input_file, output_file, direction)

    input_file = './graphml/simple1.graphml'
    output_file = './target/simple1.md'
    convert(input_file, output_file, direction)

    input_file = './graphml/simple2.graphml'
    output_file = './target/simple2.md'
    convert(input_file, output_file, direction)
    
    input_file = './graphml/simple3.graphml'
    output_file = './target/simple3.md'
    convert(input_file, output_file, direction)
