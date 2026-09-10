FROM funding-registry:local
COPY src /app/src
COPY migrations /app/migrations
COPY config /app/config
COPY tests/sqlserver_smoke.py /test/sqlserver_smoke.py
ENV PYTHONPATH=/app/src
CMD ["python", "/test/sqlserver_smoke.py"]
