# HCNetSDK needs glibc. The Supervisor's default base is Alpine/musl, so we pin
# a Debian-slim + Python base explicitly and intentionally ignore BUILD_FROM.
ARG BUILD_FROM
FROM python:3.12-slim-bookworm

# HA passes the target arch; used to pick the right HCNetSDK build.
ARG BUILD_ARCH=amd64

# HCNetSDK components dynamically link a handful of system libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libusb-1.0-0 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir aiohttp==3.9.5

# Fetch the Hikvision Device Network SDK (Linux) libraries at build time.
# Override SDK_MIRROR to use the official download or your own mirror.
ARG SDK_MIRROR="https://raw.githubusercontent.com/pergolafabio/Hikvision-Addons/main/hikvision-doorbell"
COPY fetch-sdk.sh /tmp/fetch-sdk.sh
RUN bash /tmp/fetch-sdk.sh "${BUILD_ARCH}" "${SDK_MIRROR}" /opt/hcnetsdk \
    && rm /tmp/fetch-sdk.sh
ENV LD_LIBRARY_PATH=/opt/hcnetsdk:/opt/hcnetsdk/HCNetSDKCom

COPY rootfs/opt/bridge/ /opt/bridge/
WORKDIR /opt/bridge

CMD ["python", "-u", "__main__.py"]
