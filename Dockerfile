# Use the public Alpine wgrib2 image (no auth needed)
FROM peter-mount/wgrib2:latest

# Install utilities
RUN apk add --no-cache curl python3 py3-pip bash coreutils

WORKDIR /app

COPY process.sh /app/process.sh
COPY server.py /app/server.py
COPY start.sh /app/start.sh
RUN chmod +x /app/*.sh

VOLUME ["/data"]
ENV OUTDIR=/data

EXPOSE 8080

CMD ["/app/start.sh"]
