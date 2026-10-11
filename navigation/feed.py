"""Bounded latest-complete-line reader; never replay a backlog as fresh evidence."""
from pathlib import Path


def latest(path: Path, model, limit: int = 262144):
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            start = max(0, size - limit)
            stream.seek(start)
            data = stream.read(limit)
    except FileNotFoundError:
        return None
    if start:
        # The first bytes may begin partway through a record.
        _, separator, data = data.partition(b"\n")
        if not separator:
            raise ValueError(f"{path.name}: record exceeds read limit")
    lines = data.split(b"\n")[:-1]  # Ignore an in-progress write.
    if not lines:
        return None
    # A malformed newest complete record invalidates input; never fall back.
    return model.model_validate_json(lines[-1])


def map_svg(preview, decision) -> str:
    """Camera positions only: no free-space or obstacle classification."""
    radius = preview.settings.radius_cells
    cell = 32
    width = (2 * radius + 1) * cell
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{max(width, 480)}" '
             f'height="{width + 90}" viewBox="0 0 {max(width, 480)} {width + 90}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="sans-serif" font-size="13" fill="#111">',
             '<text x="8" y="20">PREVIEW: motors disabled; obstacle clearance unknown</text>',
             '<text x="8" y="40">Blue: visited camera cells; green: camera; yellow: goal</text>']
    for z in range(-radius, radius + 1):
        for x in range(-radius, radius + 1):
            key = (x, z)
            color = "#a9ccf5" if key in preview.visits else "#eee"
            if key == decision.goal_cell:
                color = "#ffd866"
            if key == decision.camera_cell:
                color = "#6cce8a"
            parts.append(f'<rect x="{(x + radius) * cell}" y="{60 + (z + radius) * cell}" '
                         f'width="{cell - 1}" height="{cell - 1}" fill="{color}"/>')
    parts.append('</g></svg>')
    return "\n".join(parts)
