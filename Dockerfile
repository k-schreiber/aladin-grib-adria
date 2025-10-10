# Use the dtgeo/meteo-gfs-linux-alpine-wgrib2 image
FROM dtgeo/meteo-gfs-linux-alpine-wgrib2:latest

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
