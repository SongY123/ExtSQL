FROM postgres:18.4

LABEL org.opencontainers.image.title="ExtSQL PostgreSQL Extensions"
LABEL org.opencontainers.image.description="PostgreSQL 18.4 image with time-series, spatial, routing, grid, point-cloud, vector, text-search, graph, semi-structured, and hierarchical extensions."

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PG_SEARCH_VERSION=0.24.1
ARG PG_JSONSCHEMA_VERSION=0.3.4

USER root

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        lsb-release \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        "postgresql-${PG_MAJOR}-timescaledb" \
        "postgresql-${PG_MAJOR}-postgis-3" \
        "postgresql-${PG_MAJOR}-postgis-3-scripts" \
        "postgresql-${PG_MAJOR}-mobilitydb" \
        "postgresql-${PG_MAJOR}-pgrouting" \
        "postgresql-${PG_MAJOR}-pgrouting-scripts" \
        "postgresql-${PG_MAJOR}-h3" \
        "postgresql-${PG_MAJOR}-pointcloud" \
        "postgresql-${PG_MAJOR}-pgvector" \
        "postgresql-${PG_MAJOR}-age" \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    codename="$(lsb_release --codename --short)"; \
    curl -fsSL -o /tmp/groonga-apt-source.deb "https://packages.groonga.org/debian/groonga-apt-source-latest-${codename}.deb"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/groonga-apt-source.deb; \
    rm -f /tmp/groonga-apt-source.deb; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        "postgresql-${PG_MAJOR}-pgdg-pgroonga" \
        groonga-tokenizer-mecab \
        groonga-plugin-language-model \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    codename="$(lsb_release --codename --short)"; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64|arm64) ;; *) echo "Unsupported architecture for pg_search: $arch" >&2; exit 1 ;; esac; \
    deb="/tmp/postgresql-${PG_MAJOR}-pg-search_${PG_SEARCH_VERSION}-1PARADEDB-${codename}_${arch}.deb"; \
    curl -fsSL -o "$deb" "https://github.com/paradedb/paradedb/releases/download/v${PG_SEARCH_VERSION}/postgresql-${PG_MAJOR}-pg-search_${PG_SEARCH_VERSION}-1PARADEDB-${codename}_${arch}.deb"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$deb"; \
    rm -f "$deb"; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64|arm64) ;; *) echo "Unsupported architecture for pg_jsonschema: $arch" >&2; exit 1 ;; esac; \
    deb="/tmp/pg_jsonschema-v${PG_JSONSCHEMA_VERSION}-pg${PG_MAJOR}-${arch}-linux-gnu.deb"; \
    curl -fsSL -o "$deb" "https://github.com/supabase/pg_jsonschema/releases/download/v${PG_JSONSCHEMA_VERSION}/pg_jsonschema-v${PG_JSONSCHEMA_VERSION}-pg${PG_MAJOR}-${arch}-linux-gnu.deb"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$deb"; \
    rm -f "$deb"; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    { \
        echo ""; \
        echo "# Required by TimescaleDB and ParadeDB pg_search."; \
        echo "shared_preload_libraries = 'timescaledb,pg_search'"; \
        echo "timescaledb.telemetry_level = off"; \
    } >> "/usr/share/postgresql/${PG_MAJOR}/postgresql.conf.sample"

COPY sql/enable_extensions.sql /docker-entrypoint-initdb.d/10-enable-extensions.sql

RUN set -eux; \
    extension_dir="/usr/share/postgresql/${PG_MAJOR}/extension"; \
    test -r /docker-entrypoint-initdb.d/10-enable-extensions.sql; \
    for extension in \
        timescaledb \
        postgis \
        postgis_topology \
        postgis_raster \
        postgis_sfcgal \
        mobilitydb \
        pgrouting \
        h3 \
        h3_postgis \
        pointcloud \
        pointcloud_postgis \
        vector \
        pg_trgm \
        pg_search \
        pgroonga \
        age \
        pg_jsonschema \
        hstore \
        ltree \
    ; do \
        test -f "${extension_dir}/${extension}.control"; \
    done
