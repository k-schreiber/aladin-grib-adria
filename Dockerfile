# Use the NOAA-EMC wgrib2 image
FROM ghcr.io/noaa-emc/wgrib2:latest

RUN apt-get update && apt-get install -y --no-install-recommends     curl ca-certificates python3 python3-pip cron gzip bzip2 &&     rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY process.sh /app/process.sh
COPY server.py /app/server.py
COPY start.sh /app/start.sh
RUN chmod +x /app/*.sh

VOLUME ["/data"]
ENV OUTDIR=/data

EXPOSE 8080

CMD ["/app/start.sh"]
