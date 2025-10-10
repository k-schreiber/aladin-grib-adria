# Add build args for GHCR credentials
ARG GHCR_USERNAME
ARG GHCR_TOKEN

# Base image
FROM ghcr.io/noaa-emc/wgrib2:latest

# Log in to GHCR for Fly.io remote builder
RUN echo $GHCR_TOKEN | docker login ghcr.io -u $GHCR_USERNAME --password-stdin || true

# Install required utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates python3 python3-pip cron gzip bzip2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY process.sh /app/process.sh
COPY server.py /app/server.py
COPY start.sh /app/start.sh
RUN chmod +x /app/*.sh

VOLUME ["/data"]
ENV OUTDIR=/data
EXPOSE 8080

CMD ["/app/start.sh"]
