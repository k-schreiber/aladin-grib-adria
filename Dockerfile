FROM ubuntu:22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install CDO with all projection support. Without recommends: they pulled in a Debian
# Python stack (numpy 1.21, matplotlib 3.5, ...) and the ncview GUI libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    cdo \
    libeccodes-tools \
    nco \
    && rm -rf /var/lib/apt/lists/*

# Install system packages and Python 3 pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python libraries in ONE resolver pass. copernicusmarine needs numpy 2, so matplotlib
# must be a numpy-2 build too (3.10 is the last series that supports Python 3.10).
# The import check fails the build, not a run, if the combination ever breaks.
RUN pip3 install --no-cache-dir \
    flask \
    requests \
    beautifulsoup4 \
    "numpy>=2.1" \
    "matplotlib>=3.10,<3.11" \
    copernicusmarine==2.5.1 \
    eccodes==2.50.1 \
    eccodeslib==2.48.0.26 \
    eckitlib==2.1.1.26 \
 && python3 -c "import numpy, matplotlib.pyplot, copernicusmarine, eccodes, xarray, h5netcdf, flask, requests, bs4; assert int(numpy.__version__.split('.')[0]) >= 2; assert eccodes.codes_get_api_version().startswith('2.48'); print('imports OK')"

# Set working directory
WORKDIR /app

# Copy application files
COPY load_and_merge_gribs.py region.py marine_grib.py grib_validate.py server.py start.sh process.cron adriatic_coastline.json /app/
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
