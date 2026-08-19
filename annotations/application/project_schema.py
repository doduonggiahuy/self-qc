from django.db import transaction
from xml.etree import ElementTree

from annotations.models import LabelAttribute, LabelClass, Rule, SkeletonEdge, SkeletonPoint

SKELETON_POINT_COLORS = (
    "#ff4d4f", "#fa8c16", "#fadb14", "#52c41a", "#13c2c2",
    "#1677ff", "#2f54eb", "#722ed1", "#eb2f96", "#a0d911",
    "#08979c", "#d46b08", "#389e0d", "#531dab", "#c41d7f",
)


def normalize_cvat_labels(labels):
    """Convert CVAT Raw labels (including skeleton SVG) to our normalized schema."""
    normalized = []
    for source in labels:
        if source.get("deleted"):
            continue
        if "points" in source:
            normalized.append(source)
            continue
        raw_type = source.get("type", "any")
        label_type = "rectangle" if raw_type == "any" else raw_type
        item = {
            "name": source.get("name", ""), "color": source.get("color", "#38bdf8"),
            "type": label_type, "cvat_type": raw_type,
            "attributes": [attribute for attribute in source.get("attributes", []) if not attribute.get("deleted")],
            "points": [], "edges": [],
        }
        if label_type == "skeleton":
            sublabels = source.get("sublabels", [])
            by_id = {str(label.get("id")): label for label in sublabels}
            by_name = {label.get("name"): label for label in sublabels}
            node_names = {}
            try:
                root = ElementTree.fromstring(f"<svg>{source.get('svg', '')}</svg>")
            except ElementTree.ParseError:
                root = None
            if root is not None:
                for circle in root.findall("circle"):
                    sublabel = by_id.get(circle.get("data-label-id")) or by_name.get(circle.get("data-label-name"))
                    if not sublabel:
                        continue
                    node_id = circle.get("data-node-id") or circle.get("data-element-id")
                    node_names[node_id] = sublabel["name"]
                    item["points"].append({"name": sublabel["name"], "color": sublabel.get("color", "#40c4ff"), "x": float(circle.get("cx", 50)), "y": float(circle.get("cy", 50))})
                for line in root.findall("line"):
                    source_name = node_names.get(line.get("data-node-from"))
                    target_name = node_names.get(line.get("data-node-to"))
                    if source_name and target_name:
                        item["edges"].append({"from": source_name, "to": target_name})
            if not item["points"]:
                item["points"] = [{"name": label["name"], "color": label.get("color", "#40c4ff"), "x": 50, "y": 50} for label in sublabels]
        normalized.append(item)
    return normalized


@transaction.atomic
def create_project_schema(project, labels, rules):
    """Persist the CVAT-inspired project schema from the constructor payload."""
    labels = normalize_cvat_labels(labels)
    colors = ["#22c55e", "#38bdf8", "#f43f5e", "#a78bfa", "#f59e0b"]
    for order, spec in enumerate(labels):
        label = LabelClass.objects.create(
            client_project=project,
            name=spec["name"].strip(),
            label_type={"any": "rectangle"}.get(spec.get("type", "rectangle"), spec.get("type", "rectangle")),
            color=spec.get("color") or colors[order % len(colors)],
            confidence=float(spec.get("confidence", 0.25)),
            order=order,
        )
        for attr_order, attr in enumerate(spec.get("attributes", [])):
            values = attr.get("values", [])
            if isinstance(values, str):
                values = [value.strip() for value in values.split(",") if value.strip()]
            LabelAttribute.objects.create(
                label=label, name=attr["name"].strip(), input_type=attr.get("input_type", "select"),
                values=values, default_value=str(attr.get("default_value", "")),
                mutable=bool(attr.get("mutable", False)), order=attr_order,
            )
        points = {}
        for point_order, point in enumerate(spec.get("points", [])):
            points[point["name"]] = SkeletonPoint.objects.create(
                label=label, name=point["name"].strip(),
                color=point.get("color") or SKELETON_POINT_COLORS[point_order % len(SKELETON_POINT_COLORS)],
                x=float(point.get("x", 50)), y=float(point.get("y", 50)), order=point_order,
            )
        for edge_order, edge in enumerate(spec.get("edges", [])):
            if edge.get("from") in points and edge.get("to") in points:
                SkeletonEdge.objects.create(label=label, from_point=points[edge["from"]], to_point=points[edge["to"]], order=edge_order)
    for spec in rules:
        name = str(spec.get("name", "")).strip()
        if name:
            Rule.objects.create(client_project=project, name=name, description=str(spec.get("description", "")), enabled=bool(spec.get("enabled", True)))
