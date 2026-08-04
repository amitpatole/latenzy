FROM python:3.12-slim

COPY . /src
RUN pip install --no-cache-dir /src && rm -rf /src

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod 0555 /entrypoint.sh && useradd --system --no-create-home latenzy
USER latenzy

ENTRYPOINT ["/entrypoint.sh"]
CMD ["latenzy", "run", "-c", "/etc/latenzy/latenzy.yaml"]
