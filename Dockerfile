FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common curl git build-essential \
    llvm-10 llvm-10-dev libssl-dev libbz2-dev libreadline-dev \
    libsqlite3-dev zlib1g-dev libncurses5-dev libffi-dev \
    wget make liblzma-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.12 from source
RUN cd /usr/src && \
    wget https://www.python.org/ftp/python/3.12.3/Python-3.12.3.tgz && \
    tar xzf Python-3.12.3.tgz && \
    cd Python-3.12.3 && \
    ./configure --enable-optimizations && \
    make -j$(nproc) && make altinstall && \
    ln -sf /usr/local/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/local/bin/pip3.12 /usr/bin/pip3


# Set working directory
WORKDIR /pelagica

# Copy project
COPY . .

RUN apt-get update && \
    apt-get install -y r-base && \
    pip3 install --upgrade pip && \
    pip3 install poetry && \
    poetry config virtualenvs.create false && \
    poetry install && \
    pip3 install rembg



ENV LLVM_CONFIG=/usr/bin/llvm-config-10

CMD ["bash"]

