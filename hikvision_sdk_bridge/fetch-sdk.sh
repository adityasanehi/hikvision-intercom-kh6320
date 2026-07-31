#!/usr/bin/env bash
# Build-time fetch of the Hikvision HCNetSDK Linux libraries for the target arch.
# Usage: fetch-sdk.sh <build_arch> <mirror_base> <dest_dir>
#
# The libraries are Hikvision's freely-distributable Device Network SDK, mirrored
# by the well-known pergolafabio/Hikvision-Addons project. To use the official
# download or your own mirror instead, override SDK_MIRROR at build time, or copy
# the libs into ./hcnetsdk and switch the Dockerfile to COPY (see get-sdk.sh).
set -euo pipefail

BUILD_ARCH="${1:-amd64}"
MIRROR="${2:?mirror base required}"
DEST="${3:?dest dir required}"

case "$BUILD_ARCH" in
  amd64|x86_64)        LIBDIR="lib-amd64" ;;
  aarch64|arm64|arm64v8) LIBDIR="lib-aarch64" ;;
  *) echo "Unsupported arch: $BUILD_ARCH (need amd64 or aarch64)" >&2; exit 1 ;;
esac

BASE="${MIRROR%/}/${LIBDIR}"
mkdir -p "$DEST/HCNetSDKCom"

ROOT_FILES="libhcnetsdk.so libHCCore.so libhpr.so libNPQos.so libPlayCtrl.so \
libSuperRender.so libAudioRender.so libcrypto.so libcrypto.so.1.0.0 \
libssl.so libz.so libopenal.so.1 HCNetSDK_Log_Switch.xml"

COM_FILES="libAudioIntercom.so libHCAlarm.so libHCCoreDevCfg.so libHCDisplay.so \
libHCGeneralCfgMgr.so libHCIndustry.so libHCPlayBack.so libHCPreview.so \
libHCVoiceTalk.so libStreamTransClient.so libSystemTransform.so \
libanalyzedata.so libiconv2.so"

echo "Fetching HCNetSDK ($LIBDIR) from $BASE"
for f in $ROOT_FILES; do
  curl -fsSL "$BASE/$f" -o "$DEST/$f"
done
for f in $COM_FILES; do
  curl -fsSL "$BASE/HCNetSDKCom/$f" -o "$DEST/HCNetSDKCom/$f"
done

test -s "$DEST/libhcnetsdk.so" || { echo "libhcnetsdk.so missing" >&2; exit 2; }
echo "HCNetSDK ready in $DEST:"
ls -1 "$DEST" | sed 's/^/  /'
