FROM ubuntu:22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install CDO with all projection support
RUN apt-get update && apt-get install -y \
    cdo \
    libeccodes-tools \
    ncview \
    nco \
    && rm -rf /var/lib/apt/lists/*

# Install system packages and Python 3 pip
RUN apt-get update && apt-get install -y \
    cron \
    python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python libraries
RUN pip3 install --no-cache-dir \
    flask \
    requests \
    beautifulsoup4

# Set working directory
WORKDIR /app

# Copy application files
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