FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends g++ cmake make libzstd-dev nlohmann-json3-dev libtclap-dev catch2 git && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
