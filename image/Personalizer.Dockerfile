FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 xz-utils util-linux dosfstools && rm -rf /var/lib/apt/lists/*
COPY private_image.py boot_config.py /tool/
CMD ["python3", "/tool/private_image.py"]
