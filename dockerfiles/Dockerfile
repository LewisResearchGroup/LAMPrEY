FROM ubuntu:24.04

SHELL ["/bin/bash", "-c"]

ENV PYTHONUNBUFFERED=1

RUN mkdir /data /compute /static /appmedia /datalake

# Get OS version info
RUN cat /etc/os-release

RUN apt-get update && \
    apt-get install -y build-essential time curl wget libicu-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh

RUN chmod +x Miniforge3-Linux-x86_64.sh && bash Miniforge3-Linux-x86_64.sh -b -p /opt/conda \
    && rm -f Miniforge3-Linux-x86_64.sh

# Downgrade conda python to python 3.10
RUN /opt/conda/bin/conda install -y python=3.10
ENV PATH="/opt/conda/bin:${PATH}"

# allow running dotnet without ICU globalization data if needed
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

# install .NET Core runtimes so MaxQuantCmd.exe dependencies are available
RUN curl -SL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --channel 2.1 --install-dir /usr/share/dotnet \
    && /tmp/dotnet-install.sh --channel 3.1 --install-dir /usr/share/dotnet \
    && /tmp/dotnet-install.sh --version 8.0.302 --install-dir /usr/share/dotnet \
    && ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet \
    && rm /tmp/dotnet-install.sh

# add uv package really fast for installations; fail the image build if runtime deps are missing
# MaxQuant 2.4.12.0 is provided via the bundled asset under /app/seed/defaults/maxquant.
# Keep the old conda-packaged 2.0.3.0 line disabled until/if multi-version support is revisited.
RUN /opt/conda/bin/conda install --override-channels -c conda-forge -c bioconda pip uv rawtools mono
# RUN /opt/conda/bin/conda install --override-channels -c conda-forge -c bioconda maxquant=2.0.3.0

COPY requirements.txt requirements.txt

# add this to avoid issues with matplotlib installation
ENV MPLCONFIGDIR=/tmp/matplotlib
RUN mkdir -p "${MPLCONFIGDIR}" && chmod 1777 "${MPLCONFIGDIR}"

# add uv to install with increased timeout for large packages
ENV UV_HTTP_TIMEOUT=300
RUN /opt/conda/bin/uv pip install --python /opt/conda/bin/python --no-cache -r requirements.txt

RUN chown 1000:1000 /data /compute /static /appmedia /datalake

COPY ./app /app

# ensure plotly asset is available locally for dash (even without collectstatic)
RUN mkdir -p /app/main/static/dash/component_data/plotly/package_data \
    && cp /opt/conda/lib/python3.10/site-packages/plotly/package_data/plotly.min.js \
         /app/main/static/dash/component_data/plotly/package_data/plotly.min.js

WORKDIR /app/

RUN command -v /opt/conda/bin/uv \
    && command -v /opt/conda/bin/rawtools.sh \
    && command -v /opt/conda/bin/mono \
    && command -v dotnet \
    && /opt/conda/bin/mono --version \
    && dotnet --list-runtimes

RUN /opt/conda/bin/python /app/scripts/runtime_smoke_check.py
