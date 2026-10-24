"""Tiny namespace-agnostic XML helpers for TCX and GPX."""

from __future__ import annotations

import xml.etree.ElementTree as ET


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if local_name(child.tag) == name]


def child(element: ET.Element, name: str) -> ET.Element | None:
    for candidate in element:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def child_text(element: ET.Element, name: str) -> str | None:
    found = child(element, name)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element.iter() if local_name(item.tag) == name]


def first_descendant_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    wanted = set(names)
    for item in element.iter():
        if local_name(item.tag) in wanted and item.text:
            value = item.text.strip()
            if value:
                return value
    return None
