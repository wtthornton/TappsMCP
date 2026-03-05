# Node.js Security Best Practices

## Dependency Supply Chain Security

npm ecosystem risks require proactive defense:

```bash
# Audit dependencies for known vulnerabilities
npm audit
npm audit --audit-level=high

# Use lockfile for reproducible installs
npm ci  # (not npm install in CI)

# Pin exact versions to prevent unexpected updates
npm config set save-exact true
```

Use `socket.dev` or `snyk` for deeper supply chain analysis. Enable npm provenance (`--provenance`) in published packages to verify build origin.

## Prototype Pollution

Prototype pollution allows attackers to modify `Object.prototype`:

```typescript
// VULNERABLE: recursive merge without protection
function merge(target: any, source: any) {
  for (const key in source) {
    target[key] = source[key]; // allows __proto__ injection
  }
}

// SAFE: block dangerous keys
const BLOCKED_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function safeMerge(target: Record<string, unknown>, source: Record<string, unknown>) {
  for (const key of Object.keys(source)) {
    if (BLOCKED_KEYS.has(key)) continue;
    if (typeof source[key] === "object" && source[key] !== null) {
      target[key] = safeMerge(
        (target[key] as Record<string, unknown>) ?? {},
        source[key] as Record<string, unknown>,
      );
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

// BEST: use Object.create(null) for dictionary objects
const dict: Record<string, string> = Object.create(null);
```

Libraries like `lodash.merge` and `defu` have addressed this. Always update to patched versions.

## ReDoS (Regular Expression Denial of Service)

Vulnerable regex patterns cause catastrophic backtracking:

```typescript
// VULNERABLE: nested quantifiers
const emailRegex = /^([a-zA-Z0-9]+)*@example\.com$/;
// Attack string: "aaaaaaaaaaaaaaaaaa!"

// SAFE: use atomic groups or possessive quantifiers
// Or better, use a validated library:
import { z } from "zod";
const email = z.string().email();

// Use `re2` for guaranteed O(n) regex
import RE2 from "re2";
const safeRegex = new RE2("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$");
```

Use `safe-regex2` or `recheck` to audit regex patterns in your codebase.

## Helmet and HTTP Security Headers

```typescript
import helmet from "helmet";

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https:"],
    },
  },
  hsts: { maxAge: 31536000, includeSubDomains: true, preload: true },
  referrerPolicy: { policy: "strict-origin-when-cross-origin" },
}));
```

## CSRF Protection

```typescript
import { doubleCsrf } from "csrf-csrf";

const { doubleCsrfProtection, generateToken } = doubleCsrf({
  getSecret: () => process.env.CSRF_SECRET!,
  cookieName: "__csrf",
  cookieOptions: { httpOnly: true, sameSite: "strict", secure: true },
});

app.use(doubleCsrfProtection);

// Provide token to frontend
app.get("/csrf-token", (req, res) => {
  res.json({ token: generateToken(req, res) });
});
```

## Input Validation and Sanitization

Never trust user input:

```typescript
import { z } from "zod";
import DOMPurify from "isomorphic-dompurify";

// Validate structure and types
const UserInput = z.object({
  name: z.string().min(1).max(100).trim(),
  bio: z.string().max(500).transform((v) => DOMPurify.sanitize(v)),
  age: z.coerce.number().int().min(0).max(150),
});

// SQL injection prevention: always use parameterized queries
const user = await db.query("SELECT * FROM users WHERE id = $1", [userId]);
// NEVER: `SELECT * FROM users WHERE id = '${userId}'`
```

## Secret Management

```typescript
// Never hardcode secrets
// BAD:  const apiKey = "sk-abc123...";
// GOOD: const apiKey = process.env.API_KEY;

// Validate required env vars at startup
const requiredEnvVars = ["DATABASE_URL", "JWT_SECRET", "API_KEY"];
for (const envVar of requiredEnvVars) {
  if (!process.env[envVar]) {
    throw new Error(`Missing required environment variable: ${envVar}`);
  }
}

// Use dotenv only in development
if (process.env.NODE_ENV !== "production") {
  const { config } = await import("dotenv");
  config();
}
```

## Rate Limiting and Abuse Prevention

```typescript
import rateLimit from "express-rate-limit";

// Tiered rate limiting
const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 5 });
const apiLimiter = rateLimit({ windowMs: 60 * 1000, max: 100 });

app.use("/api/auth/login", authLimiter);
app.use("/api/", apiLimiter);
```
