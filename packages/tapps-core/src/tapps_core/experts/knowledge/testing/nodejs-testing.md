# Node.js Testing Patterns

## Vitest Configuration

Vitest is the recommended test runner for modern Node.js/TypeScript projects:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node", // or "jsdom" for browser APIs
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      thresholds: { lines: 80, branches: 75, functions: 80 },
    },
    testTimeout: 10000,
    hookTimeout: 30000,
  },
});
```

## Mocking ESM Modules

ESM mocking requires `vi.mock()` with factory functions:

```typescript
// Mock a module
vi.mock("./database", () => ({
  getConnection: vi.fn().mockResolvedValue({ query: vi.fn() }),
}));

// Mock a default export
vi.mock("node-fetch", () => ({
  default: vi.fn(),
}));

// Spy on a real module (partial mock)
vi.mock("./utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./utils")>();
  return { ...actual, formatDate: vi.fn().mockReturnValue("2026-01-01") };
});

// Reset mocks between tests
afterEach(() => { vi.restoreAllMocks(); });
```

## Jest Patterns (Legacy)

Jest still dominates in existing codebases:

```typescript
// Manual mock in __mocks__/fs.ts
const fs = jest.createMockFromModule<typeof import("fs")>("fs");
export default fs;

// Snapshot testing
expect(renderComponent(props)).toMatchSnapshot();

// Asymmetric matchers
expect(result).toEqual(expect.objectContaining({
  id: expect.any(String),
  createdAt: expect.any(Date),
}));
```

## Playwright E2E Testing

Playwright provides cross-browser E2E testing:

```typescript
import { test, expect } from "@playwright/test";

test("user login flow", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByText("Dashboard")).toBeVisible();
});

// Page Object Model
class LoginPage {
  constructor(private page: Page) {}
  async login(email: string, password: string) {
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: "Sign In" }).click();
  }
}
```

## Test Containers (Testcontainers)

Use real databases in integration tests:

```typescript
import { PostgreSqlContainer } from "@testcontainers/postgresql";

let container: StartedPostgreSqlContainer;

beforeAll(async () => {
  container = await new PostgreSqlContainer("postgres:16")
    .withDatabase("testdb")
    .start();
  process.env.DATABASE_URL = container.getConnectionUri();
}, 60000);

afterAll(async () => { await container.stop(); });
```

## Testing Async Code

```typescript
// Test async errors
await expect(async () => {
  await fetchUser("invalid-id");
}).rejects.toThrow("User not found");

// Test event emitters
test("emits data event", async () => {
  const stream = createReadStream("file.txt");
  const data = await new Promise<Buffer>((resolve) => {
    stream.on("data", resolve);
  });
  expect(data).toBeDefined();
});

// Fake timers
vi.useFakeTimers();
const callback = vi.fn();
setTimeout(callback, 1000);
vi.advanceTimersByTime(1000);
expect(callback).toHaveBeenCalled();
vi.useRealTimers();
```

## HTTP Testing

Test HTTP handlers with `supertest`:

```typescript
import request from "supertest";
import { app } from "./app";

test("GET /api/users returns 200", async () => {
  const res = await request(app)
    .get("/api/users")
    .set("Authorization", "Bearer token")
    .expect(200);
  expect(res.body).toHaveLength(3);
});
```

## Coverage and CI Integration

```yaml
# .github/workflows/test.yml
- run: npx vitest --coverage --reporter=junit --outputFile=results.xml
- uses: actions/upload-artifact@v4
  with:
    name: coverage
    path: coverage/lcov.info
```
