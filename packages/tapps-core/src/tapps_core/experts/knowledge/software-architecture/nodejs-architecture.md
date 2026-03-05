# Node.js Architecture Patterns

## ESM vs CommonJS

Node.js supports both module systems. Prefer ESM for new projects:

```json
// package.json - enable ESM
{ "type": "module" }
```

```typescript
// ESM imports
import { readFile } from "node:fs/promises";
import { join } from "node:path";

// Dynamic import (works in both ESM and CJS)
const module = await import("./plugin.js");

// __dirname equivalent in ESM
import { fileURLToPath } from "node:url";
const __dirname = fileURLToPath(new URL(".", import.meta.url));
```

Key differences: ESM is async, uses strict mode by default, and supports top-level `await`. CJS files use `.cjs` extension (or no `"type": "module"` in package.json).

## Monorepo with Turborepo

Structure large Node.js projects as monorepos:

```
my-project/
  apps/
    web/          # Next.js frontend
    api/          # Express/Fastify backend
  packages/
    shared/       # Shared types and utilities
    ui/           # Shared UI components
    config/       # Shared ESLint, TypeScript configs
  turbo.json
  package.json
```

```json
// turbo.json
{
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "test": { "dependsOn": ["build"] },
    "lint": {},
    "dev": { "cache": false, "persistent": true }
  }
}
```

Nx alternative: use `nx.json` with project graph and affected commands for larger monorepos (100+ packages).

## Event-Driven Architecture

Use EventEmitter for decoupled communication:

```typescript
import { EventEmitter } from "node:events";

// Typed events
interface OrderEvents {
  created: [order: Order];
  paid: [order: Order, payment: Payment];
  shipped: [order: Order, tracking: string];
  cancelled: [order: Order, reason: string];
}

class OrderService extends (EventEmitter as new () => TypedEmitter<OrderEvents>) {
  async createOrder(data: CreateOrderDto): Promise<Order> {
    const order = await this.repository.save(data);
    this.emit("created", order);
    return order;
  }
}

// Subscribe from other services
orderService.on("created", async (order) => {
  await emailService.sendConfirmation(order);
  await analyticsService.trackOrder(order);
});
```

## Worker Threads for CPU-Bound Work

Offload CPU-intensive tasks to worker threads:

```typescript
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";

if (isMainThread) {
  function runWorker(data: unknown): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const worker = new Worker(new URL(import.meta.url), { workerData: data });
      worker.on("message", resolve);
      worker.on("error", reject);
    });
  }

  const result = await runWorker({ file: "large-dataset.csv" });
} else {
  // Worker thread
  const result = processData(workerData);
  parentPort?.postMessage(result);
}
```

Use a worker pool (`piscina` or `workerpool`) for production:

```typescript
import Piscina from "piscina";
const pool = new Piscina({ filename: "./worker.js", maxThreads: 4 });
const result = await pool.run({ task: "parse", data: rawData });
```

## Graceful Shutdown

Handle process signals for clean shutdown:

```typescript
const server = app.listen(3000);
const connections = new Set<Socket>();

server.on("connection", (conn) => {
  connections.add(conn);
  conn.on("close", () => connections.delete(conn));
});

async function shutdown(signal: string) {
  console.log(`Received ${signal}. Starting graceful shutdown...`);
  server.close();
  for (const conn of connections) conn.destroy();
  await database.disconnect();
  await cache.quit();
  process.exit(0);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
```

## Dependency Injection Without Frameworks

Lightweight DI using factory functions:

```typescript
// Container pattern
function createContainer(config: AppConfig) {
  const db = createDatabase(config.databaseUrl);
  const cache = createRedisClient(config.redisUrl);
  const userRepo = createUserRepository(db);
  const userService = createUserService(userRepo, cache);
  const userController = createUserController(userService);
  return { db, cache, userService, userController };
}

const container = createContainer(loadConfig());
app.use("/users", container.userController.router);
```

## Structured Logging

Use `pino` for high-performance structured logging:

```typescript
import pino from "pino";

const logger = pino({
  level: process.env.LOG_LEVEL ?? "info",
  transport: process.env.NODE_ENV === "development"
    ? { target: "pino-pretty" }
    : undefined,
});

// Child loggers for request context
app.use((req, res, next) => {
  req.log = logger.child({ requestId: req.headers["x-request-id"] });
  next();
});
```
