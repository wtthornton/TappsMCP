# Time-Series Databases

## InfluxDB

### Line Protocol

InfluxDB ingests data via the line protocol format:

```
measurement,tag1=val1,tag2=val2 field1=1.0,field2="str" timestamp_ns
```

Example:

```
temperature,location=office,sensor=dht22 value=23.5,humidity=45.2 1709654400000000000
cpu,host=server01,region=us-east usage_idle=95.2,usage_system=2.1 1709654400000000000
```

Tags are indexed (use for filtering), fields are not (use for values). Keep tag cardinality under 100k per measurement.

### Flux Queries

Flux is InfluxDB's functional query language:

```flux
// Basic query with filtering and aggregation
from(bucket: "iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "temperature")
  |> filter(fn: (r) => r.location == "office")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> yield(name: "mean_temperature")

// Join two measurements
temp = from(bucket: "iot_data") |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "temperature")
humidity = from(bucket: "iot_data") |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "humidity")
join(tables: {temp: temp, humidity: humidity}, on: ["_time", "location"])

// Anomaly detection with moving average
from(bucket: "metrics")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "response_time")
  |> movingAverage(n: 12)
  |> map(fn: (r) => ({r with anomaly: r._value > 500.0}))
```

### Retention Policies and Downsampling

```flux
// Create a downsampling task (runs every hour)
option task = {name: "downsample_1h", every: 1h}

from(bucket: "raw_data")
  |> range(start: -task.every)
  |> filter(fn: (r) => r._measurement == "sensor_readings")
  |> aggregateWindow(every: 1h, fn: mean)
  |> to(bucket: "downsampled_1h", org: "myorg")
```

Set bucket retention: raw data 7 days, hourly aggregates 90 days, daily aggregates 2 years.

## TimescaleDB

TimescaleDB extends PostgreSQL with hypertables for time-series data:

```sql
-- Create hypertable
CREATE TABLE sensor_data (
  time        TIMESTAMPTZ NOT NULL,
  sensor_id   TEXT NOT NULL,
  temperature DOUBLE PRECISION,
  humidity    DOUBLE PRECISION
);

SELECT create_hypertable('sensor_data', by_range('time'));

-- Automatic compression (after 7 days)
ALTER TABLE sensor_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'sensor_id',
  timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('sensor_data', INTERVAL '7 days');

-- Continuous aggregate (materialized view that auto-updates)
CREATE MATERIALIZED VIEW sensor_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', time) AS bucket,
  sensor_id,
  avg(temperature) AS avg_temp,
  max(temperature) AS max_temp,
  min(temperature) AS min_temp
FROM sensor_data
GROUP BY bucket, sensor_id;

-- Auto-refresh policy
SELECT add_continuous_aggregate_policy('sensor_hourly',
  start_offset => INTERVAL '3 hours',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour');

-- Retention policy
SELECT add_retention_policy('sensor_data', INTERVAL '30 days');
```

## Best Practices

### Schema Design
- Use timestamps as the primary ordering dimension
- Keep tag/label cardinality bounded (avoid unique IDs as tags)
- Batch writes for throughput (1000-5000 points per request)
- Align time buckets to natural boundaries (minute, hour, day)

### Query Optimization
- Always filter by time range first
- Use pre-aggregated continuous aggregates for dashboards
- Avoid `SELECT *` on raw data for large time ranges
- Use `LIMIT` or `last()` for latest-value queries

### Capacity Planning
- Raw data: estimate `points_per_second * bytes_per_point * retention_seconds`
- InfluxDB: ~2-8 bytes per field value (compressed)
- TimescaleDB: ~40-100 bytes per row (compressed with segmentby)
- Downsampling reduces storage by 10-100x per aggregation tier
