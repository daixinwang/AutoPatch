# Python fixture sandbox. Build explicitly before running an external repository.
# For other toolchains, use a reviewed image with its locked dependencies preinstalled.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir pytest==8.3.5
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /workspace
