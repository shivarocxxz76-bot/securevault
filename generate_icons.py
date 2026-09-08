"""
Generate PWA icons for SecureVault.
Run: python generate_icons.py
Requires: pip install Pillow
"""
import os, struct, zlib, math

def create_svg_icon(size):
    """Create a teal/navy shield icon as SVG."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0a0d14"/>
      <stop offset="100%" style="stop-color:#0d1a2a"/>
    </linearGradient>
    <linearGradient id="shield" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#00d4d4"/>
      <stop offset="100%" style="stop-color:#4f46e5"/>
    </linearGradient>
  </defs>
  <!-- Background rounded rect -->
  <rect width="512" height="512" rx="96" fill="url(#bg)"/>
  <!-- Outer glow ring -->
  <rect width="512" height="512" rx="96" fill="none" stroke="rgba(0,212,212,0.15)" stroke-width="12"/>
  <!-- Shield shape -->
  <path d="M256 80 L400 140 L400 260 Q400 360 256 430 Q112 360 112 260 L112 140 Z"
        fill="url(#shield)" opacity="0.2"/>
  <path d="M256 100 L385 155 L385 260 Q385 350 256 415 Q127 350 127 260 L127 155 Z"
        fill="none" stroke="url(#shield)" stroke-width="8" stroke-linejoin="round"/>
  <!-- Lock body -->
  <rect x="196" y="250" width="120" height="95" rx="16" fill="#00d4d4"/>
  <!-- Lock shackle -->
  <path d="M216 250 L216 218 Q216 180 256 180 Q296 180 296 218 L296 250"
        fill="none" stroke="#00d4d4" stroke-width="20" stroke-linecap="round"/>
  <!-- Keyhole -->
  <circle cx="256" cy="290" r="14" fill="#0a0d14"/>
  <rect x="249" y="290" width="14" height="22" rx="4" fill="#0a0d14"/>
  <!-- SV text -->
  <text x="256" y="395" font-family="Arial,sans-serif" font-size="42" font-weight="900"
        fill="#00d4d4" text-anchor="middle" letter-spacing="-1">SV</text>
</svg>"""
    return svg


def save_png_from_svg(svg_content, filepath, size):
    """Save SVG as a simple PNG using Pillow if available, else save as SVG fallback."""
    try:
        from PIL import Image
        import io

        # Try cairosvg first
        try:
            import cairosvg
            png_bytes = cairosvg.svg2png(bytestring=svg_content.encode(), output_width=size, output_height=size)
            with open(filepath, 'wb') as f:
                f.write(png_bytes)
            print(f"  Created (cairosvg): {filepath}")
            return True
        except ImportError:
            pass

        # Fallback: create a programmatic PNG with Pillow
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(img)

        # Background rounded rectangle
        margin = 0
        draw.rounded_rectangle([margin, margin, size-margin, size-margin],
                                radius=int(size*0.18),
                                fill=(10, 13, 20, 255))

        # Teal border
        draw.rounded_rectangle([margin+4, margin+4, size-margin-4, size-margin-4],
                                radius=int(size*0.17),
                                fill=None, outline=(0, 212, 212, 60), width=max(2, size//60))

        # Shield gradient simulation (teal circle)
        cx, cy = size//2, int(size*0.42)
        r = int(size*0.28)
        for i in range(r, 0, -1):
            alpha = int(30 * (1 - i/r))
            color = (0, 212, 212, alpha)
            draw.ellipse([cx-i, cy-i, cx+i, cy+i], fill=color)

        # Lock icon (simplified)
        lw, lh = int(size*0.22), int(size*0.18)
        lx, ly = cx - lw//2, cy - lh//4
        draw.rounded_rectangle([lx, ly, lx+lw, ly+lh], radius=max(3, size//30), fill=(0, 212, 212, 255))

        # Shackle
        sw = max(3, size//25)
        sx = cx - int(size*0.07)
        draw.arc([sx, ly-int(size*0.14), sx+int(size*0.14), ly+int(size*0.06)],
                 start=180, end=0, fill=(0, 212, 212, 255), width=sw)

        # "SV" text
        try:
            font_size = max(16, size//5)
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        text = "SV"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw//2, ly + lh + int(size*0.04)), text,
                  fill=(0, 212, 212, 255), font=font)

        img.save(filepath, 'PNG')
        print(f"  Created (Pillow): {filepath}")
        return True

    except ImportError:
        # Save as SVG with .png extension (browser will still load it if served correctly)
        svg_path = filepath.replace('.png', '.svg')
        with open(svg_path, 'w') as f:
            f.write(svg_content)
        print(f"  Saved SVG fallback: {svg_path}")
        return False


def main():
    img_dir = os.path.join('app', 'static', 'img')
    os.makedirs(img_dir, exist_ok=True)

    sizes = [72, 96, 128, 144, 152, 192, 384, 512]

    print("Generating SecureVault PWA icons...")
    for size in sizes:
        svg = create_svg_icon(size)
        path = os.path.join(img_dir, f'icon-{size}.png')
        save_png_from_svg(svg, path, size)

    print("\nDone! Icons saved to app/static/img/")
    print("\nIf icons show as SVG fallback, install Pillow:")
    print("  pip install Pillow")
    print("Or CairoSVG for best quality:")
    print("  pip install cairosvg")


if __name__ == '__main__':
    main()
