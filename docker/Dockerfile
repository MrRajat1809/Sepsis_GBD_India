# xpdf pdftotext
FROM python:3.13.1-slim-bookworm AS xpdf
ARG XPDF_VERSION=4.00
ARG XPDF_SHA256=ff3d92c42166e35b1ba6aec9b5f0adffb5fc05a3eb95dc49505b6e344e4216d6
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates cmake curl g++ make \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://dl.xpdfreader.com/old/xpdf-${XPDF_VERSION}.tar.gz" -o /tmp/xpdf.tar.gz \
    && echo "${XPDF_SHA256}  /tmp/xpdf.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/xpdf.tar.gz -C /tmp \
    && cmake -S "/tmp/xpdf-${XPDF_VERSION}" -B /tmp/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="-std=gnu++14" \
    && cmake --build /tmp/build --target pdftotext -j"$(nproc)" \
    && install -m 0755 /tmp/build/xpdf/pdftotext /usr/local/bin/pdftotext

# Environment
FROM python:3.13.1-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHELL=/bin/bash

COPY --from=xpdf /usr/local/bin/pdftotext /usr/local/bin/pdftotext

WORKDIR /workspace

# Packages
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m pip check \
    && pdftotext -v 2>&1 | grep -q 'version 4.00'

# JupyterLab
EXPOSE 8888
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root"]
