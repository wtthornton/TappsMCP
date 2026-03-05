# IoT Observability Patterns

## MQTT Quality of Service Levels

MQTT provides three QoS levels for message delivery:

- **QoS 0 (At most once)** - Fire and forget. No acknowledgment. Use for high-frequency sensor data where occasional loss is acceptable.
- **QoS 1 (At least once)** - Guaranteed delivery with PUBACK. May deliver duplicates. Use for alerts and commands.
- **QoS 2 (Exactly once)** - Four-step handshake (PUBREC, PUBREL, PUBCOMP). Use for billing or critical state changes.

```python
# Python (paho-mqtt)
import paho.mqtt.client as mqtt

client = mqtt.Client(protocol=mqtt.MQTTv5)
client.connect("broker.example.com", 1883)

# Telemetry: QoS 0 (high frequency, loss acceptable)
client.publish("sensors/temp/office-1", payload="23.5", qos=0)

# Alert: QoS 1 (must be delivered)
client.publish("alerts/temperature/high", payload='{"sensor":"office-1","temp":35.0}', qos=1)

# Command: QoS 2 (exactly once)
client.publish("commands/hvac/office-1/set", payload='{"target":22.0}', qos=2)
```

### Topic Hierarchy Design

```
{org}/{site}/{area}/{device_type}/{device_id}/{data_type}

sensors/factory-a/line-1/temperature/dht22-001/reading
sensors/factory-a/line-1/temperature/dht22-001/status
commands/factory-a/line-1/hvac/unit-01/set
alerts/factory-a/line-1/temperature/dht22-001/high
```

Use `+` for single-level wildcard, `#` for multi-level: `sensors/factory-a/+/temperature/#`.

## Telegraf Collection

Telegraf is the standard agent for collecting IoT metrics:

```toml
# telegraf.conf

# MQTT input for sensor data
[[inputs.mqtt_consumer]]
  servers = ["tcp://broker.example.com:1883"]
  topics = ["sensors/#"]
  qos = 0
  data_format = "json"
  topic_tag = "topic"
  json_time_key = "timestamp"
  json_time_format = "unix_ms"

# System metrics from the edge device
[[inputs.cpu]]
  percpu = false
  totalcpu = true

[[inputs.mem]]
[[inputs.disk]]
  mount_points = ["/"]

[[inputs.net]]
  interfaces = ["eth0", "wlan0"]

# Output to InfluxDB
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  token = "${INFLUX_TOKEN}"
  organization = "myorg"
  bucket = "iot_raw"

# Buffer for network interruptions (edge resilience)
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  [outputs.influxdb_v2.buffer]
    metric_buffer_limit = 100000
    metric_batch_size = 5000
```

## Edge Telemetry Patterns

### Store-and-Forward

Buffer data locally when connectivity is intermittent:

```python
import sqlite3
import json
from datetime import datetime, UTC

class EdgeBuffer:
    """Local SQLite buffer for offline telemetry."""

    def __init__(self, db_path: str = "/var/lib/telemetry/buffer.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                sent INTEGER DEFAULT 0
            )
        """)

    def enqueue(self, topic: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO buffer (topic, payload, timestamp) VALUES (?, ?, ?)",
            (topic, json.dumps(payload), datetime.now(tz=UTC).isoformat()),
        )
        self.conn.commit()

    def flush(self, mqtt_client, batch_size: int = 100) -> int:
        rows = self.conn.execute(
            "SELECT id, topic, payload FROM buffer WHERE sent = 0 LIMIT ?",
            (batch_size,),
        ).fetchall()
        sent = 0
        for row_id, topic, payload in rows:
            result = mqtt_client.publish(topic, payload, qos=1)
            if result.rc == 0:
                self.conn.execute("UPDATE buffer SET sent = 1 WHERE id = ?", (row_id,))
                sent += 1
        self.conn.commit()
        return sent
```

### Data Aggregation at the Edge

Reduce bandwidth by pre-aggregating at the edge:

```python
from collections import defaultdict
from statistics import mean, stdev

class EdgeAggregator:
    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self.buffers: dict[str, list[float]] = defaultdict(list)

    def add(self, sensor_id: str, value: float) -> None:
        self.buffers[sensor_id].append(value)

    def flush(self) -> dict[str, dict[str, float]]:
        results = {}
        for sensor_id, values in self.buffers.items():
            if values:
                results[sensor_id] = {
                    "mean": mean(values),
                    "min": min(values),
                    "max": max(values),
                    "stddev": stdev(values) if len(values) > 1 else 0.0,
                    "count": len(values),
                }
        self.buffers.clear()
        return results
```

## Grafana Dashboards for IoT

### Dashboard Structure

Organize IoT dashboards in a hierarchy:
1. **Overview** - fleet health, active devices, alert summary
2. **Site view** - per-location metrics, geographic map
3. **Device detail** - individual device telemetry, diagnostics

### Key Panels

```json
{
  "panels": [
    {
      "title": "Device Online Status",
      "type": "stat",
      "description": "Percentage of devices reporting in last 5 minutes"
    },
    {
      "title": "Temperature Heatmap",
      "type": "heatmap",
      "description": "Temperature distribution across all sensors"
    },
    {
      "title": "Data Ingestion Rate",
      "type": "timeseries",
      "description": "Messages per second by site"
    },
    {
      "title": "Alert Timeline",
      "type": "logs",
      "description": "Recent alerts with severity and device context"
    }
  ]
}
```

### Alerting Rules

```yaml
# Grafana alerting rule
- alert: DeviceOffline
  expr: time() - last_seen_timestamp > 300
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Device {{ $labels.device_id }} has not reported for 5+ minutes"

- alert: TemperatureAnomaly
  expr: abs(temperature - avg_over_time(temperature[1h])) > 3 * stddev_over_time(temperature[1h])
  for: 2m
  labels:
    severity: critical
```
