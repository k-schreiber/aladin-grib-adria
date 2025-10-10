# Use the dtgeo/meteo-gfs-linux-alpine-wgrib2 image
FROM dtgeo/meteo-gfs-linux-alpine-wgrib2:latest

# Configure APK repos (optional but safer)
RUN echo "http://dl-cdn.alpinelinux.org/alpine/v3.20/main" > /etc/apk/repositories && \
    echo "http://dl-cdn.alpinelinux.org/alpine/v3.20/community" >> /etc/apk/repositories

# Install required packages
RUN apk update && apk add --no-cache \
    bash python3 py3-pip py3-flask curl gzip bzip2 coreutils ca-certificates dcron gawk

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
