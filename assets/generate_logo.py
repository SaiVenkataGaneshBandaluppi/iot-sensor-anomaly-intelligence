"""Generate the project SVG logo programmatically."""

from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "logo.svg"

SVG_WIDTH = 400
SVG_HEIGHT = 120

BACKGROUND_COLOR = "#0d1117"
PRIMARY_COLOR = "#00d4ff"
SECONDARY_COLOR = "#0077aa"
ACCENT_COLOR = "#ff6b35"
TEXT_COLOR = "#e6edf3"
GRID_COLOR = "#1c2333"


def _wave_path(x_start: float, y_center: float, amplitude: float, wavelength: float, points: int) -> str:
    import math

    coords = []
    for i in range(points):
        x = x_start + i * (wavelength / points)
        phase = (i / points) * 2 * math.pi
        y = y_center + amplitude * math.sin(phase)
        coords.append(f"{x:.1f},{y:.1f}")
    return "M " + " L ".join(coords)


def generate_svg() -> str:
    wave1 = _wave_path(20, 60, 18, 200, 40)
    wave2 = _wave_path(20, 60, 10, 180, 40)

    circuit_nodes = [(30, 55), (80, 42), (130, 68), (180, 45), (230, 62)]
    node_circles = "\n    ".join(
        f'<circle cx="{x}" cy="{y}" r="4" fill="{PRIMARY_COLOR}" opacity="0.9"/>'
        for x, y in circuit_nodes
    )
    node_lines = "\n    ".join(
        f'<line x1="{circuit_nodes[i][0]}" y1="{circuit_nodes[i][1]}" x2="{circuit_nodes[i + 1][0]}" y2="{circuit_nodes[i + 1][1]}" stroke="{SECONDARY_COLOR}" stroke-width="1.5" opacity="0.6"/>'
        for i in range(len(circuit_nodes) - 1)
    )

    anomaly_x, anomaly_y = 130, 68
    anomaly_spike = (
        f'<polyline points="{anomaly_x - 15},{anomaly_y} {anomaly_x - 5},{anomaly_y - 25} '
        f'{anomaly_x},{anomaly_y + 20} {anomaly_x + 5},{anomaly_y - 18} {anomaly_x + 15},{anomaly_y}" '
        f'fill="none" stroke="{ACCENT_COLOR}" stroke-width="2" stroke-linejoin="round"/>'
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{BACKGROUND_COLOR};stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#111827;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="waveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:{SECONDARY_COLOR};stop-opacity:0.4"/>
      <stop offset="50%" style="stop-color:{PRIMARY_COLOR};stop-opacity:0.9"/>
      <stop offset="100%" style="stop-color:{SECONDARY_COLOR};stop-opacity:0.4"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" rx="10" fill="url(#bgGrad)"/>

  <line x1="0" y1="30" x2="{SVG_WIDTH}" y2="30" stroke="{GRID_COLOR}" stroke-width="1"/>
  <line x1="0" y1="60" x2="{SVG_WIDTH}" y2="60" stroke="{GRID_COLOR}" stroke-width="0.5"/>
  <line x1="0" y1="90" x2="{SVG_WIDTH}" y2="90" stroke="{GRID_COLOR}" stroke-width="1"/>

  <path d="{wave2}" fill="none" stroke="{SECONDARY_COLOR}" stroke-width="1.5" opacity="0.4"/>
  <path d="{wave1}" fill="none" stroke="url(#waveGrad)" stroke-width="2.5" filter="url(#glow)"/>

  {node_lines}
  {node_circles}
  {anomaly_spike}

  <rect x="248" y="25" width="4" height="50" rx="2" fill="{GRID_COLOR}"/>

  <text x="260" y="48" font-family="'Courier New', monospace" font-size="20" font-weight="700" fill="{TEXT_COLOR}" letter-spacing="0.5">IoT Anomaly</text>
  <text x="260" y="72" font-family="'Courier New', monospace" font-size="13" font-weight="400" fill="{PRIMARY_COLOR}" letter-spacing="1.5">INTELLIGENCE</text>
  <text x="260" y="90" font-family="'Courier New', monospace" font-size="9" fill="{SECONDARY_COLOR}" opacity="0.7" letter-spacing="0.8">SENSOR ANALYSIS PLATFORM</text>
</svg>"""
    return svg


def main() -> None:
    svg_content = generate_svg()
    OUTPUT_FILE.write_text(svg_content)
    print(f"Logo saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
