可以。按照你现在的设计，我建议单条样本保持很轻量，`extensions`用对象列表表示，每个扩展只记录`type`和`name`，安装来源和开启SQL放在枚举说明里，不必在每条样本里重复。

## 完整JSON样例

```json
{
  "id": "objsql_spatial_000001",
  "database": {
    "db_id": "nyc_poi",
    "engine": "PostgreSQL",
    "engine_version": "18",
    "extensions": [
      {
        "type": "spatial",
        "name": "postgis"
      }
    ]
  },
  "question": "Find restaurants within 5 km of Central Park and return the 5 restaurants nearest to The Mount Sinai Hospital. Return their names, locations, and distances to the hospital in meters.",
  "sql": "WITH anchors AS (SELECT MAX(CASE WHEN name = 'Central Park' THEN geom END) AS central_park_geom, MAX(CASE WHEN name = 'The Mount Sinai Hospital' THEN geom END) AS hospital_geom FROM landmarks) SELECT r.name, ST_AsText(r.geom) AS location, ST_Distance(r.geom::geography, a.hospital_geom::geography) AS distance_to_hospital_m FROM restaurants r CROSS JOIN anchors a WHERE ST_DWithin(r.geom::geography, a.central_park_geom::geography, 5000) ORDER BY r.geom <-> a.hospital_geom LIMIT 5;",
  "sql_objects": [
    {
      "type": "data_type",
      "value": "geometry"
    },
    {
      "type": "data_type",
      "value": "geography"
    },
    {
      "type": "function",
      "value": "ST_DWithin"
    },
    {
      "type": "function",
      "value": "ST_Distance"
    },
    {
      "type": "function",
      "value": "ST_AsText"
    },
    {
      "type": "operator",
      "value": "::"
    },
    {
      "type": "operator",
      "value": "<->"
    }
  ],
  "object_categories": [
    "Structured"
  ],
  "difficulty": "hard"
}
```

如果整个标注文件包含多条样本，可以直接用数组：

```json
[
  {
    "id": "objsql_spatial_000001",
    "database": {
      "db_id": "nyc_poi",
      "engine": "PostgreSQL",
      "engine_version": "18",
      "extensions": [
        {
          "type": "spatial",
          "name": "postgis"
        }
      ]
    },
    "question": "...",
    "sql": "...",
    "sql_objects": [],
    "object_categories": [
      "Structured"
    ],
    "difficulty": "hard"
  }
]
```

## 字段说明

```json
{
  "id": "string, unique instance identifier",
  "database": {
    "db_id": "string, target database identifier",
    "engine": "enum, currently PostgreSQL",
    "engine_version": "enum, currently 18",
    "extensions": "array of enabled PostgreSQL extensions"
  },
  "question": "string, natural language question",
  "sql": "string, gold SQL query",
  "sql_objects": "array of required SQL objects",
  "object_categories": "array of data-oriented object categories",
  "difficulty": "enum, difficulty level of the instance"
}
```

## 枚举字段说明

### `database.engine`

当前固定为：

```json
["PostgreSQL"]
```

### `database.engine_version`

当前固定为：

```json
["18"]
```

### `database.extensions[].type`

可选值如下：

```json
[
  "time_series",
  "spatial",
  "spatio_temporal",
  "routing_network",
  "spatial_grid",
  "point_cloud",
  "vector",
  "text_search",
  "graph",
  "semi_structured",
  "hierarchical"
]
```

### `database.extensions[].name`参照image/README_zh.md中“扩展对应关系和开启 SQL”表格中的`插件/扩展`列。

### `sql_objects[].type`

可选值如下：

```json
[
  "data_type",
  "function",
  "operator"
]
```

含义如下：

| value       | meaning                                                      |
| ----------- | ------------------------------------------------------------ |
| `data_type` | SQL数据类型，例如`geometry`、`geography`、`vector`、`jsonb`、`tsvector` |
| `function`  | 数据库函数，例如`ST_DWithin`、`ST_Distance`、`time_bucket`、`ts_rank`   |
| `operator`  | SQL操作符，例如`::`、`<->`、`->>`、`@>`、`@@`                          |

### `object_categories`

可选值如下：

```json
[
  "Structured",
  "Semi-Structured",
  "Unstructured"
]
```

含义如下：

| value             | meaning                              |
| ----------------- | ------------------------------------ |
| `Structured`      | 面向结构化数据的SQL对象，例如时序、空间、图结构相关对象        |
| `Semi-Structured` | 面向半结构化数据的SQL对象，例如JSON、数组、嵌套属性相关对象    |
| `Unstructured`    | 面向非结构化数据的SQL对象，例如全文检索、向量检索、多媒体特征相关对象 |

该字段可以是多标签。例如，一个SQL同时使用JSON字段和向量检索时，可以写成：

```json
"object_categories": [
  "Semi-Structured",
  "Unstructured"
]
```

### `difficulty`

建议使用四档：

```json
[
  "easy",
  "medium",
  "hard",
  "extra_hard"
]
```

含义如下：

| value        | meaning                                                  |
| ------------ |----------------------------------------------------------|
| `easy`       | 只涉及单一SQL object，SQL结构较简单                                 |
| `medium`     | 涉及2个SQL objects，或需要与过滤、排序、聚合等常规SQL结构组合                   |
| `hard`       | 需要3+个SQL objects协同使用，并包含复杂SQL结构，如CTE、JOIN、Top-k、分组或多条件约束 |
| `extra_hard` | 涉及跨类别SQL objects、复杂嵌套查询、图遍历、时空推理或多阶段检索与聚合                |
