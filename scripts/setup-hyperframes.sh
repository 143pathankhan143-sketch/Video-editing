#!/usr/bin/env bash
set -euo pipefail

# Persistent HyperFrames runtime setup for /home/user/Video-editing
# Ensures Node dependencies, static FFmpeg 9.x, FFprobe, Chromium 153 headless-shell,
# and Devanagari fonts (Mukta) are installed and ready.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d "node_modules/hyperframes" ]; then
  echo "[setup-hyperframes] Installing npm packages..."
  npm install
fi

sudo mkdir -p /opt/hyperframes-deps/bin /opt/hyperframes-deps/lib /opt/hyperframes-deps/swiftshader

# 1. FFprobe from @ffprobe-installer
if [ ! -x /opt/hyperframes-deps/bin/ffprobe ]; then
  FFPROBE_SRC="$(node -e "console.log(require('@ffprobe-installer/ffprobe').path)")"
  sudo cp -f "$FFPROBE_SRC" /opt/hyperframes-deps/bin/ffprobe
  sudo chmod +x /opt/hyperframes-deps/bin/ffprobe
  sudo ln -sf /opt/hyperframes-deps/bin/ffprobe /usr/local/bin/ffprobe
fi

# 2. FFmpeg (prefer modern static build from /tmp/venv imageio-ffmpeg, fallback to @ffmpeg-installer/ffmpeg)
if [ ! -x /opt/hyperframes-deps/bin/ffmpeg ]; then
  if [ -x /tmp/venv/bin/python ]; then
    FFMPEG_SRC="$(/tmp/venv/bin/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)"
  else
    FFMPEG_SRC=""
  fi
  if [ -z "$FFMPEG_SRC" ] || [ ! -f "$FFMPEG_SRC" ]; then
    FFMPEG_SRC="$(node -e "console.log(require('@ffmpeg-installer/ffmpeg').path)")"
  fi
  sudo cp -f "$FFMPEG_SRC" /opt/hyperframes-deps/bin/ffmpeg
  sudo chmod +x /opt/hyperframes-deps/bin/ffmpeg
  sudo ln -sf /opt/hyperframes-deps/bin/ffmpeg /usr/local/bin/ffmpeg
fi

# 3. Chromium Headless Shell + NSS/NSPR + SwiftShader from @sparticuz/chromium
if [ ! -x /opt/hyperframes-deps/bin/chrome-headless-shell-bin ]; then
  echo "[setup-hyperframes] Extracting headless Chromium & shared libraries..."
  node -e '
    const fs = require("fs");
    const zlib = require("zlib");
    const path = require("path");
    const { execSync } = require("child_process");
    const binDir = path.resolve("node_modules/@sparticuz/chromium/bin");

    fs.writeFileSync("/tmp/hf_chromium_bin", zlib.brotliDecompressSync(fs.readFileSync(path.join(binDir, "chromium.br"))));
    fs.chmodSync("/tmp/hf_chromium_bin", 0o755);

    fs.writeFileSync("/tmp/hf_al2023.tar", zlib.brotliDecompressSync(fs.readFileSync(path.join(binDir, "al2023.tar.br"))));
    execSync("sudo tar -xf /tmp/hf_al2023.tar -C /opt/hyperframes-deps");

    fs.writeFileSync("/tmp/hf_swift.tar", zlib.brotliDecompressSync(fs.readFileSync(path.join(binDir, "swiftshader.tar.br"))));
    execSync("sudo tar -xf /tmp/hf_swift.tar -C /opt/hyperframes-deps/swiftshader");
    execSync("rm -f /tmp/hf_al2023.tar /tmp/hf_swift.tar");
  '
  sudo mv -f /tmp/hf_chromium_bin /opt/hyperframes-deps/bin/chrome-headless-shell-bin
  sudo chmod +x /opt/hyperframes-deps/bin/chrome-headless-shell-bin

  sudo tee /opt/hyperframes-deps/bin/chromium >/dev/null << 'WRAP'
#!/usr/bin/env bash
export LD_LIBRARY_PATH="/opt/hyperframes-deps/lib:/opt/hyperframes-deps/swiftshader:${LD_LIBRARY_PATH:-}"
exec /opt/hyperframes-deps/bin/chrome-headless-shell-bin --no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage "$@"
WRAP
  sudo chmod +x /opt/hyperframes-deps/bin/chromium
  sudo ln -sf /opt/hyperframes-deps/bin/chromium /opt/hyperframes-deps/bin/chrome-headless-shell
  sudo ln -sf /opt/hyperframes-deps/bin/chromium /usr/bin/chromium
  sudo ln -sf /opt/hyperframes-deps/bin/chromium /usr/bin/chromium-browser
fi

# 4. Install Mukta Devanagari fonts system-wide
if [ -d "$ROOT_DIR/assets/fonts" ]; then
  sudo mkdir -p /usr/share/fonts/truetype/mukta
  sudo cp -f "$ROOT_DIR"/assets/fonts/*.ttf /usr/share/fonts/truetype/mukta/ 2>/dev/null || true
  sudo fc-cache -f >/dev/null 2>&1 || true
fi

export HYPERFRAMES_BROWSER_PATH="/opt/hyperframes-deps/bin/chrome-headless-shell"

# 5. Regenerate enhanced 1080x1920 source proxy for HyperFrames project if missing (gitignored to keep repo light)
if [ -f "$ROOT_DIR/VID-20261112-WA0002.mp4" ] && [ ! -f "$ROOT_DIR/hyperframes-property/assets/video/source_hd.mp4" ]; then
  echo "[setup-hyperframes] Building 1080x1920 enhanced source video for HyperFrames..."
  mkdir -p "$ROOT_DIR/hyperframes-property/assets/video"
  ffmpeg -y -i "$ROOT_DIR/VID-20261112-WA0002.mp4" \
    -vf "scale=1080:1920:flags=lanczos,eq=gamma=1.14:saturation=1.12:contrast=1.05,unsharp=5:5:0.65:5:5:0.0" \
    -c:v libx264 -preset fast -crf 23 -g 15 -pix_fmt yuv420p \
    -an -movflags +faststart \
    "$ROOT_DIR/hyperframes-property/assets/video/source_hd.mp4"
fi

echo "[setup-hyperframes] Ready! Browser: $HYPERFRAMES_BROWSER_PATH"
