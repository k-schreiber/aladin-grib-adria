# Use the dtgeo/meteo-gfs-linux-alpine-wgrib2 image
FROM dtgeo/meteo-gfs-linux-alpine-wgrib2:latest

# Install bash and other utilities
RUN apk add --no-cache bash python3 py3-pip curl gzip bzip2 coreutils awk ca-certificates busybox-cron

# Install Python modules
RUN pip3 install --no-cache-dir flask

# Set working directory
WORKDIR /app

# Copy your application files
COPY process.sh server.py start.sh /app/
RUN chmod +x /app/*.sh

# Set environment variables
ENV OUTDIR=/data

# Expose the port the app will run on
EXPOSE 8080

# Command to run the application
CMD ["/app/start.sh"]
