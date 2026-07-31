#!/usr/bin/env bash
# Lay out the Hikvision Device Network SDK (Linux64) libraries into ./hcnetsdk
# so the add-on image can bundle them.
#
# The SDK is distributed by Hikvision (free, for use with their devices) from
# https://www.hikvision.com/en/support/download/sdk/  ->  "Device Network SDK"
# Pick the Linux64 (amd64) package; for a Raspberry Pi / arm64 HA host pick the
# arm64 variant instead.
#
# Usage:
#   ./get-sdk.sh /path/to/CH-HCNetSDK*Linux64*.zip
#   ./get-sdk.sh /path/to/extracted/sdk/dir
#
# Result: ./hcnetsdk/{libhcnetsdk.so,libHCCore.so,libhpr.so,libcrypto*,libssl*,
#          HCNetSDKCom/*}
set -euo pipefail

SRC="${1:-}"
DEST="$(cd "$(dirname "$0")" && pwd)/hcnetsdk"

if [[ -z "$SRC" ]]; then
  echo "usage: $0 <sdk-zip|sdk-dir>" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ -f "$SRC" ]]; then
  echo "Extracting $SRC ..."
  unzip -q -o "$SRC" -d "$WORK"
  ROOT="$WORK"
else
  ROOT="$SRC"
fi

mkdir -p "$DEST/HCNetSDKCom"

# Copy the core libs wherever they sit inside the package.
find "$ROOT" -type f \( -name 'libhcnetsdk.so*' -o -name 'libHCCore.so*' \
  -o -name 'libhpr.so*' -o -name 'libcrypto.so*' -o -name 'libssl.so*' \
  -o -name 'libz.so*' -o -name 'libSuperRender.so*' -o -name 'libAudioRender.so*' \) \
  -exec cp -av {} "$DEST/" \;

# Copy the whole component directory.
COMDIR="$(find "$ROOT" -type d -name 'HCNetSDKCom' | head -1 || true)"
if [[ -n "$COMDIR" ]]; then
  cp -av "$COMDIR/." "$DEST/HCNetSDKCom/"
fi

echo
echo "Done. Bundled into $DEST:"
ls -1 "$DEST"
echo "HCNetSDKCom/:"
ls -1 "$DEST/HCNetSDKCom" | head
[[ -f "$DEST/libhcnetsdk.so" ]] || { echo "!! libhcnetsdk.so missing" >&2; exit 2; }
