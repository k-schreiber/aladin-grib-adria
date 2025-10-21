# Use the dtgeo/meteo-gfs-linux-alpine-wgrib2 image
FROM dtgeo/meteo-gfs-linux-alpine-wgrib2:latest

# Configure APK repos (optional but safer)
RUN echo "http://dl-cdn.alpinelinux.org/alpine/v3.20/main" > /etc/apk/repositories && \
    echo "http://dl-cdn.alpinelinux.org/alpine/v3.20/community" >> /etc/apk/repositories

# Install required packages
RUN apk update && apk add --no-cache \
    bash python3 py3-pip py3-flask curl gzip bzip2 coreutils ca-certificates dcron gawk \
    py3-requests py3-beautifulsoup4

# Set working directory
WORKDIR /app

# Copy your application files
COPY load_and_merge_gribs.py server.py start.sh process.cron /app/
RUN chmod +x /app/*.sh /app/*.py

# Install crontab
RUN crontab /app/process.cron

# Set environment variables
ENV OUTDIR=/data

# Create data directory
RUN mkdir -p /data /tmp/aladin

# Expose the port the app will run on
EXPOSE 8080

# Command to run the application
CMD ["/app/start.sh"]
