ARG BUILD_FROM=python:3.12-slim-bookworm
FROM ${BUILD_FROM}

# HCNetSDK components dynamically link a handful of system libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libusb-1.0-0 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir aiohttp==3.9.5

# Hikvision Device Network SDK (Linux). Provided in the build context under
# ./hcnetsdk (see get-sdk.sh / DOCS.md). Contains libhcnetsdk.so, libHCCore.so,
# libhpr.so, libcrypto/ssl and the HCNetSDKCom/ component directory.
COPY hcnetsdk/ /opt/hcnetsdk/
ENV LD_LIBRARY_PATH=/opt/hcnetsdk:/opt/hcnetsdk/HCNetSDKCom

COPY rootfs/opt/bridge/ /opt/bridge/
WORKDIR /opt/bridge

CMD ["python", "-u", "__main__.py"]
