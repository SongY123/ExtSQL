# ExtSQL PostgreSQL 18.4 综合扩展镜像

这个镜像以 `postgres:18.4` 为 base image，面向 ExtSQL-Bench 需要的 PostgreSQL 扩展集合。镜像安装扩展二进制和 control 文件，并把初始化 SQL 打包到 `/docker-entrypoint-initdb.d/10-enable-extensions.sql`，空数据目录首次启动时会自动启用这些扩展。

## 构建

在仓库根目录执行：

```bash
scripts/build_image.sh
```

如果要自定义镜像 tag，或传递额外的 `docker build` 参数：

```bash
scripts/build_image.sh --tag extsql-postgres:18.4-dev --no-cache
scripts/build_image.sh --platform linux/amd64
```

也可以通过环境变量设置扩展包版本：

```bash
PG_SEARCH_VERSION=0.24.1 PG_JSONSCHEMA_VERSION=0.3.4 scripts/build_image.sh
```

等价的底层 Docker 命令是在 `image` 目录下执行：

```bash
docker build -t extsql-postgres:18.4 .
```

或使用 Compose：

```bash
docker compose up -d --build
```

## 启动

```bash
docker run --name extsql-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -d extsql-postgres:18.4 \
  postgres -c shared_preload_libraries=timescaledb,pg_search \
           -c timescaledb.telemetry_level=off
```

`timescaledb` 和 `pg_search` 需要 `shared_preload_libraries`。Dockerfile 已把它写入 PostgreSQL 初始化模板；上面的启动参数用于覆盖已有数据目录时也能生效。

## 初始化扩展

镜像已经内置 `sql/enable_extensions.sql`，空 `PGDATA` 首次初始化时会自动执行。已有数据目录不会重新执行 `/docker-entrypoint-initdb.d`；如果要在已有数据库上补启用扩展，可以手动执行：

```bash
docker exec -i extsql-postgres psql -U postgres -d postgres < sql/enable_extensions.sql
```

`/docker-entrypoint-initdb.d` 只会在空 `PGDATA` 初始化时执行。

## 扩展对应关系和开启 SQL

| 类型 | 插件/扩展 | 安装来源 | 开启 SQL |
| --- | --- | --- | --- |
| time_series | `timescaledb` | PGDG package `postgresql-18-timescaledb` | `CREATE EXTENSION IF NOT EXISTS timescaledb;` |
| spatial | `postgis` | PGDG package `postgresql-18-postgis-3` | `CREATE EXTENSION IF NOT EXISTS postgis;` |
| spatial | `postgis_topology` | PGDG package `postgresql-18-postgis-3` | `CREATE EXTENSION IF NOT EXISTS postgis_topology;` |
| spatial | `postgis_raster` | PGDG package `postgresql-18-postgis-3` | `CREATE EXTENSION IF NOT EXISTS postgis_raster;` |
| spatial | `postgis_sfcgal` | PGDG package `postgresql-18-postgis-3` | `CREATE EXTENSION IF NOT EXISTS postgis_sfcgal;` |
| spatio_temporal | `mobilitydb` | PGDG package `postgresql-18-mobilitydb` | `CREATE EXTENSION IF NOT EXISTS mobilitydb;` |
| routing_network | `pgrouting` | PGDG package `postgresql-18-pgrouting` | `CREATE EXTENSION IF NOT EXISTS pgrouting;` |
| spatial_grid | `h3` | PGDG package `postgresql-18-h3` | `CREATE EXTENSION IF NOT EXISTS h3;` |
| spatial_grid | `h3_postgis` | PGDG package `postgresql-18-h3` | `CREATE EXTENSION IF NOT EXISTS h3_postgis;` |
| point_cloud | `pointcloud` | PGDG package `postgresql-18-pointcloud` | `CREATE EXTENSION IF NOT EXISTS pointcloud;` |
| point_cloud | `pointcloud_postgis` | PGDG package `postgresql-18-pointcloud` | `CREATE EXTENSION IF NOT EXISTS pointcloud_postgis;` |
| vector | `vector` | PGDG package `postgresql-18-pgvector` | `CREATE EXTENSION IF NOT EXISTS vector;` |
| text_search | `pg_trgm` | PostgreSQL contrib extension included with `postgres:18.4` | `CREATE EXTENSION IF NOT EXISTS pg_trgm;` |
| text_search | `pg_search` | ParadeDB release deb `postgresql-18-pg-search` | `CREATE EXTENSION IF NOT EXISTS pg_search;` |
| text_search | `pgroonga` | PGroonga package `postgresql-18-pgdg-pgroonga` | `CREATE EXTENSION IF NOT EXISTS pgroonga;` |
| graph | `age` | PGDG package `postgresql-18-age` | `CREATE EXTENSION IF NOT EXISTS age;` |
| semi_structured | `pg_jsonschema` | Supabase release deb `pg_jsonschema-v*-pg18-*-linux-gnu.deb` | `CREATE EXTENSION IF NOT EXISTS pg_jsonschema;` |
| semi_structured | `hstore` | PostgreSQL contrib extension included with `postgres:18.4` | `CREATE EXTENSION IF NOT EXISTS hstore;` |
| hierarchical | `ltree` | PostgreSQL contrib extension included with `postgres:18.4` | `CREATE EXTENSION IF NOT EXISTS ltree;` |

## 安装来源备注

- PostgreSQL base image: `postgres:18.4`
- PGDG packages: official PostgreSQL APT repository already configured by the Debian-based `postgres` image.
- PGroonga: official Groonga Debian repository package `groonga-apt-source-latest-trixie.deb`.
- ParadeDB `pg_search`: GitHub release deb; default build arg `PG_SEARCH_VERSION=0.24.1`.
- Supabase `pg_jsonschema`: GitHub release deb; default build arg `PG_JSONSCHEMA_VERSION=0.3.4`.
