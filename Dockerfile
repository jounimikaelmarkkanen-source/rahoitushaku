FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Official Microsoft ODBC 18 for Azure SQL, with certificate validation enabled in the app.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unixodbc \
    poppler-utils tesseract-ocr tesseract-ocr-fin tesseract-ocr-swe tesseract-ocr-eng \
    && curl -fsSLo /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/* /tmp/packages-microsoft-prod.deb
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && useradd --create-home --uid 10001 funding
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
RUN mkdir data && chown funding:funding data
USER funding
EXPOSE 8000
CMD ["uvicorn", "funding.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
