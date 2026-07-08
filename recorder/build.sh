#!/usr/bin/env bash
# Compila o voxlog-rec e empacota num .app ad-hoc-assinado (identidade TCC estável).
# Rode uma vez após clonar / após editar voxlog-rec.swift.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/voxlog-rec.app"
BIN="$APP/Contents/MacOS/voxlog-rec"

swiftc -O "$DIR/voxlog-rec.swift" -o "$DIR/voxlog-rec.bin"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
mv "$DIR/voxlog-rec.bin" "$BIN"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>voxlog-rec</string>
  <key>CFBundleDisplayName</key><string>voxlog Recorder</string>
  <key>CFBundleIdentifier</key><string>com.voxlog.recorder</string>
  <key>CFBundleExecutable</key><string>voxlog-rec</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>15.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>voxlog grava mic + audio do sistema para transcrever suas reunioes.</string>
</dict>
</plist>
PLIST
codesign --force --deep --sign - "$APP"
echo "OK → $BIN"
