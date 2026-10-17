"""Read-only Blockbench structure audit and conservative group-freeze fingerprints."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read(path):
    raw = Path(path).read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(doc, dict):
        raise ValueError("Model root must be an object")
    return doc, digest(raw)


def vector(value, length):
    return (isinstance(value, list) and len(value) == length and
            all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value))


def groups(doc):
    result = []
    definitions = doc.get("groups", [])
    by_id = {g["uuid"]: g for g in definitions}
    if len(by_id) != len(definitions):
        raise ValueError("Duplicate group UUID in group definitions")

    def walk(nodes, parents):
        if not isinstance(nodes, list):
            raise ValueError("Outliner children must be a list")
        for node in nodes:
            if isinstance(node, dict):
                node = {**by_id.get(node.get("uuid"), {}), **node}
                result.append((node, parents))
                walk(node.get("children", []), parents + [node])
            elif not isinstance(node, str):
                raise ValueError("Outliner child must be a UUID string or a group")
    walk(doc.get("outliner", []), [])
    used = {g.get("uuid") for g, _ in result}
    if set(by_id) - used:
        raise ValueError("Group definitions absent from outliner")
    return result


def texture_index(ref, textures):
    if ref is None:
        return None
    if isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < len(textures):
        return ref
    if isinstance(ref, str):
        if ref.isdigit() and int(ref) < len(textures):
            return int(ref)
        found = [i for i, t in enumerate(textures) if ref == t.get("uuid")]
        if len(found) == 1:
            return found[0]
    raise ValueError(f"Invalid texture reference: {ref!r}")


def audit(doc, sha, cuboids_only):
    errors, warnings = [], []
    elements, textures = doc.get("elements", []), doc.get("textures", [])
    if not isinstance(elements, list) or not isinstance(textures, list):
        raise ValueError("elements and textures must be lists")
    group_rows = groups(doc)
    counts = {"cubes": 0, "meshes": 0, "other_elements": 0,
              "groups": len(group_rows), "textures": len(textures), "animations": len(doc.get("animations", []))}
    seen, references, multi_axis, unsupported_angles = set(), [], 0, 0
    resolution = doc.get("resolution", {})
    if not isinstance(resolution, dict) or not all(isinstance(resolution.get(k), (int, float)) and
            not isinstance(resolution.get(k), bool) and math.isfinite(resolution[k]) and resolution[k] > 0
            for k in ("width", "height")):
        errors.append("Missing/invalid positive UV resolution")
        resolution = {"width": 0, "height": 0}
    for node, kind in [(e, "element") for e in elements] + [(g, "group") for g, _ in group_rows]:
        uid, name = node.get("uuid"), node.get("name", "unnamed")
        if not isinstance(uid, str) or not uid or uid in seen:
            errors.append(f"{kind} {name}: missing/duplicate UUID")
        seen.add(uid)
        rotation = node.get("rotation", [0, 0, 0])
        if not vector(rotation, 3):
            errors.append(f"{name}: non-finite/invalid rotation")
        else:
            multi_axis += sum(abs(x) > 1e-8 for x in rotation) > 1
            unsupported_angles += any(not any(abs(x - a) < 1e-5 for a in (-45, -22.5, 0, 22.5, 45)) for x in rotation)
        if "origin" in node and not vector(node["origin"], 3):
            errors.append(f"{name}: invalid pivot")
        if kind == "group":
            references.extend(x for x in node.get("children", []) if isinstance(x, str))
            continue
        type_name = node.get("type", "cube")
        counts["cubes" if type_name == "cube" else "meshes" if type_name == "mesh" else "other_elements"] += 1
        if type_name != "cube":
            if cuboids_only:
                errors.append(f"{name}: {type_name} is not a cuboid")
            continue
        lo, hi = node.get("from"), node.get("to")
        if not vector(lo, 3) or not vector(hi, 3):
            errors.append(f"{name}: invalid from/to")
        elif any(b <= a for a, b in zip(lo, hi)):
            errors.append(f"{name}: non-positive cuboid extent")
        for side, face in node.get("faces", {}).items():
            if face.get("texture") is None:
                continue
            try:
                ti = texture_index(face["texture"], textures)
            except ValueError as exc:
                errors.append(f"{name}/{side}: {exc}")
                continue
            uv = face.get("uv")
            if not vector(uv, 4):
                errors.append(f"{name}/{side}: invalid UV")
            else:
                tw = textures[ti].get("uv_width", resolution["width"])
                th = textures[ti].get("uv_height", resolution["height"])
                if not isinstance(tw, (int, float)) or not isinstance(th, (int, float)) or tw <= 0 or th <= 0:
                    errors.append(f"texture {ti}: invalid UV dimensions")
                elif min(uv) < 0 or max(uv[0], uv[2]) > tw or max(uv[1], uv[3]) > th:
                    warnings.append(f"{name}/{side}: UV outside texture bounds; wrapping requires review")
            fr = face.get("rotation", 0)
            if not isinstance(fr, (int, float)) or not math.isfinite(fr) or fr % 90:
                errors.append(f"{name}/{side}: unsupported UV rotation")
    references.extend(x for x in doc.get("outliner", []) if isinstance(x, str))
    element_ids = {e.get("uuid") for e in elements}
    for uid in set(references):
        if uid not in element_ids:
            errors.append(f"Dangling outliner element: {uid}")
        if references.count(uid) > 1:
            errors.append(f"Element assigned more than once: {uid}")
    for uid in element_ids - set(references):
        warnings.append(f"Element absent from outliner: {uid}")
    texture_facts = []
    for i, texture in enumerate(textures):
        source = texture.get("source", "")
        fact = {"index": i, "name": texture.get("name")}
        if isinstance(source, str) and source.startswith("data:image/png;base64,"):
            try:
                raw = base64.b64decode(source.split(",", 1)[1], validate=True)
                if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) < 24:
                    raise ValueError("Invalid PNG signature/header")
                fact.update(sha256=digest(raw), dimensions=list(struct.unpack(">II", raw[16:24])))
            except (ValueError, TypeError) as exc:
                errors.append(f"texture {i}: invalid embedded PNG ({exc})")
        else:
            warnings.append(f"texture {i}: external/non-PNG image not opened; portability and image data unverified")
        texture_facts.append(fact)
    return {"model_sha256": sha, "format": doc.get("meta", {}).get("model_format"),
            "counts": counts, "multi_axis_rotated_nodes": multi_axis,
            "nodes_with_angles_outside_java_block_set": unsupported_angles,
            "textures": texture_facts, "errors": errors, "warnings": warnings,
            "scope": "structure only; no rendering, penetration, appearance, animation or game compatibility acceptance"}


def frozen_part(doc, selector):
    found = [(g, p) for g, p in groups(doc) if selector in (g.get("uuid"), g.get("name"))]
    if len(found) != 1:
        raise ValueError(f"Group {selector!r} resolves to {len(found)} matches; use a unique UUID")
    group, parents = found[0]
    group_lookup = {g["uuid"]: g for g, _ in groups(doc)}
    elements = {e["uuid"]: e for e in doc.get("elements", [])}
    selected, textures = [], doc.get("textures", [])

    def collect(node):
        for child in node.get("children", []):
            if isinstance(child, dict):
                collect(group_lookup[child["uuid"]])
            else:
                selected.append(elements[child])
    collect(group)
    indexes = set()
    for element in selected:
        for face in element.get("faces", {}).values():
            ti = texture_index(face.get("texture"), textures)
            if ti is not None:
                indexes.add(ti)
    texture_data = []
    for ti in sorted(indexes):
        texture = textures[ti]
        source = texture.get("source", "")
        if not isinstance(source, str) or not source.startswith("data:"):
            raise ValueError(f"Locked group uses external texture {ti}; embed it before a portable fingerprint")
        texture_data.append({k: texture[k] for k in
            ("source", "uv_width", "uv_height", "width", "height", "render_mode", "render_sides") if k in texture})
    def expanded(node):
        return {**node, "children": [expanded(group_lookup[x["uuid"]]) if isinstance(x, dict) else x
                                      for x in node.get("children", [])]}
    payload = {"group": expanded(group), "elements": sorted(selected, key=lambda x: x["uuid"]),
               "ancestors": [{k: v for k, v in p.items() if k != "children"} for p in parents],
               "textures": texture_data, "resolution": doc.get("resolution"),
               "meta": doc.get("meta"), "box_uv": doc.get("box_uv")}
    return {"selector": selector, "uuid": group["uuid"], "elements": len(selected), "sha256": digest(canonical(payload))}


def emit(report, output):
    value = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(value)
        print(json.dumps({"output": str(path), "errors": len(report.get("errors", [])),
                          "warnings": len(report.get("warnings", [])), "unchanged": report.get("unchanged")}, ensure_ascii=False))
    else:
        print(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "snapshot", "compare"):
        sub = subs.add_parser(command)
        sub.add_argument("model", type=Path)
        sub.add_argument("--output", type=Path)
        if command == "audit":
            sub.add_argument("--cuboids-only", action="store_true")
        elif command == "snapshot":
            sub.add_argument("--group", action="append", required=True)
        else:
            sub.add_argument("--baseline", required=True, type=Path)
    args = parser.parse_args()
    try:
        doc, sha = read(args.model)
        if args.command == "audit":
            report = audit(doc, sha, args.cuboids_only)
            success = not report["errors"]
        elif args.command == "snapshot":
            report = {"schema": 1, "source_sha256": sha, "parts": [frozen_part(doc, x) for x in args.group]}
            success = True
        else:
            baseline, _ = read(args.baseline)
            if baseline.get("schema") != 1 or not baseline.get("parts"):
                raise ValueError("Unsupported or empty baseline")
            rows = []
            for previous in baseline["parts"]:
                current = frozen_part(doc, previous["uuid"])
                rows.append({"group": previous["selector"], "unchanged": current["sha256"] == previous["sha256"],
                             "before": previous["sha256"], "after": current["sha256"]})
            success = all(r["unchanged"] for r in rows)
            report = {"model_sha256": sha, "unchanged": success, "parts": rows}
        emit(report, args.output)
        return 0 if success else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(f"Audit stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
