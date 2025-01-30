FROM fedora:latest

EXPOSE 10389

RUN dnf install -y python3 python3-devel gcc git vim iputils util-linux-core procps-ng telnet

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir twisted pyOpenSSL service-identity

WORKDIR /app

RUN git clone https://github.com/robertlogos/ldaptor.git

COPY proxy.py /app/ldaptor/proxy.py

WORKDIR /app/ldaptor

CMD ["python", "proxy.py"]
