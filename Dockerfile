FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3-pip aircrack-ng hostapd lsof iproute2 sudo mdk4 \
    build-essential pkg-config libnl-3-dev libnl-genl-3-dev libssl-dev p7zip-full git curl && \
    ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install hostapd-mana
RUN git clone https://github.com/sensepost/hostapd-mana.git /tmp/hostapd-mana && \
    cd /tmp/hostapd-mana && \
    git checkout bd6114db0e0214003699f446dd7c4cb399efef71 && \
    cd hostapd && \
    make && \
    cp hostapd /usr/local/bin/hostapd-mana && \
    chmod +x /usr/local/bin/hostapd-mana && \
    cd / && rm -rf /tmp/hostapd-mana

# Install hashcat
RUN curl -LO https://hashcat.net/files/hashcat-6.1.1.7z && \
    7z x hashcat-6.1.1.7z && \
    mv hashcat-6.1.1 /usr/local/bin/hashcat-6.1.1 && \
    ln -sf /usr/local/bin/hashcat-6.1.1/hashcat.bin /usr/local/bin/hashcat && \
    rm hashcat-6.1.1.7z

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Create log files
RUN touch /app/app.log /app/evil_twin.log && \
    chmod 666 /app/app.log /app/evil_twin.log

COPY . .

EXPOSE 8000

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
