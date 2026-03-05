# TypeScript Code Quality Patterns

## Strict Mode Configuration

Enable strict mode in `tsconfig.json` for maximum type safety:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

Key strict flags: `strictNullChecks`, `strictFunctionTypes`, `strictBindCallApply`, `strictPropertyInitialization`, `noImplicitAny`, `noImplicitThis`, `alwaysStrict`.

## Type Guards

Use type guards to narrow union types safely:

```typescript
// User-defined type guard
function isError(value: unknown): value is Error {
  return value instanceof Error;
}

// Discriminated union guard
type Result<T> = { ok: true; value: T } | { ok: false; error: string };

function handleResult<T>(result: Result<T>): T {
  if (result.ok) {
    return result.value; // narrowed to { ok: true; value: T }
  }
  throw new Error(result.error);
}

// `satisfies` operator (TypeScript 5+)
const config = {
  port: 3000,
  host: "localhost",
} satisfies Record<string, string | number>;
```

## Branded / Opaque Types

Prevent accidental misuse of primitives with branded types:

```typescript
type UserId = string & { readonly __brand: unique symbol };
type OrderId = string & { readonly __brand: unique symbol };

function createUserId(id: string): UserId {
  if (!id.startsWith("usr_")) throw new Error("Invalid user ID format");
  return id as UserId;
}

function getUser(id: UserId): void { /* ... */ }
// getUser("raw-string")  // compile error
// getUser(orderId)        // compile error
```

## Utility Types

Built-in utility types reduce boilerplate:

```typescript
// Partial, Required, Pick, Omit for object shape manipulation
type UpdateUser = Partial<Pick<User, "name" | "email">>;

// Record for index signatures
type StatusMap = Record<HttpStatus, string>;

// Extract, Exclude for union manipulation
type NumericEvents = Extract<Event, { value: number }>;

// Awaited for unwrapping Promise types
type Data = Awaited<ReturnType<typeof fetchData>>;

// Template literal types
type EventName = `on${Capitalize<string>}`;
```

## Discriminated Unions

Model state machines with discriminated unions:

```typescript
type LoadingState =
  | { status: "idle" }
  | { status: "loading"; startedAt: number }
  | { status: "success"; data: unknown; completedAt: number }
  | { status: "error"; error: Error; retriedCount: number };

// Exhaustive checking with `never`
function render(state: LoadingState): string {
  switch (state.status) {
    case "idle": return "Ready";
    case "loading": return "Loading...";
    case "success": return `Done: ${JSON.stringify(state.data)}`;
    case "error": return `Error: ${state.error.message}`;
    default: {
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}
```

## Const Assertions and Enums

Prefer `as const` over enums for better tree-shaking:

```typescript
// Prefer this:
const HTTP_STATUS = {
  OK: 200,
  NOT_FOUND: 404,
  SERVER_ERROR: 500,
} as const;
type HttpStatus = (typeof HTTP_STATUS)[keyof typeof HTTP_STATUS];

// Over numeric enums (which generate runtime code):
// enum HttpStatus { OK = 200, NOT_FOUND = 404 }
```

## Module Augmentation

Extend third-party types without modifying source:

```typescript
// Extend Express Request
declare module "express-serve-static-core" {
  interface Request {
    userId?: string;
    tenantId?: string;
  }
}
```

## Linting and Formatting

Use `typescript-eslint` with strict type-checked rules:

```json
{
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/strict-type-checked",
    "plugin:@typescript-eslint/stylistic-type-checked"
  ],
  "parserOptions": {
    "project": "./tsconfig.json"
  }
}
```

Key rules: `no-explicit-any`, `no-unsafe-assignment`, `no-floating-promises`, `strict-boolean-expressions`, `switch-exhaustiveness-check`.
