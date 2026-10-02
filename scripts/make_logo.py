"""Draw static/logo.svg and static/icon.svg from the heading font (run once; needs fonttools + brotli).

pip install fonttools brotli && python scripts/make_logo.py
"""
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONT = "static/fonts/chakra-petch-latin-700-normal.woff2"
STOPS = '<stop offset="0" stop-color="#7fb2ff"/><stop offset="0.55" stop-color="#4f8cff"/>' \
        '<stop offset="1" stop-color="#9085e9"/>'

font = TTFont(FONT)
glyphs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
cap = font["OS/2"].sCapHeight
pad = 20


def letters(text, tracking):
    x, out = 0, []
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        out.append((x, pen.getCommands()))
        x += glyphs[name].width + tracking
    return out, x - tracking


paths, width = letters("NEXUS", int(upm * 0.22))
w, h = width + 2 * pad, cap + 2 * pad
body = "".join(f'<path transform="translate({x + pad} {cap + pad}) scale(1 -1)" d="{d}"/>'
               for x, d in paths)
with open("static/logo.svg", "w") as f:
    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w / 10:.0f}" '
            f'height="{h / 10:.0f}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">'
            f'{STOPS}</linearGradient></defs><g fill="url(#g)">{body}</g></svg>')

(x0, d), w1 = letters("N", 0)[0][0], letters("N", 0)[1]
side = max(w1, cap) + 2 * pad
with open("static/icon.svg", "w") as f:
    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" width="64" '
            f'height="64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">{STOPS}'
            f'</linearGradient></defs><path fill="url(#g)" transform="translate('
            f'{(side - w1) / 2} {cap + (side - cap) / 2}) scale(1 -1)" d="{d}"/></svg>')
print("wrote static/logo.svg and static/icon.svg")
