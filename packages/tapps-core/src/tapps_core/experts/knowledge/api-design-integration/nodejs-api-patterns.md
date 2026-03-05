# Node.js API Design Patterns

## Express Middleware Stack

Structure Express apps with layered middleware:

```typescript
import express from "express";
import helmet from "helmet";
import cors from "cors";

const app = express();

// Security middleware first
app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGINS?.split(",") }));
app.use(express.json({ limit: "1mb" }));

// Request logging
app.use((req, res, next) => {
  const start = Date.now();
  res.on("finish", () => {
    console.log(`${req.method} ${req.path} ${res.statusCode} ${Date.now() - start}ms`);
  });
  next();
});

// Error handler (must be last, 4 args)
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error(err.stack);
  res.status(500).json({ error: "Internal server error" });
});
```

## Fastify Plugins

Fastify uses an encapsulated plugin system for modularity:

```typescript
import Fastify from "fastify";

const app = Fastify({ logger: true });

// Register a plugin with encapsulated scope
app.register(async (instance) => {
  instance.decorate("db", await connectDatabase());

  instance.get("/users", async (request, reply) => {
    const users = await instance.db.query("SELECT * FROM users");
    return users;
  });
}, { prefix: "/api" });

// Schema-based validation (built-in, uses Ajv)
app.post("/users", {
  schema: {
    body: {
      type: "object",
      required: ["name", "email"],
      properties: {
        name: { type: "string", minLength: 1 },
        email: { type: "string", format: "email" },
      },
    },
    response: { 201: { type: "object", properties: { id: { type: "string" } } } },
  },
  handler: async (request, reply) => {
    const user = await createUser(request.body);
    reply.status(201).send(user);
  },
});
```

## NestJS Modules and Dependency Injection

NestJS provides Angular-style architecture for Node.js:

```typescript
// users.module.ts
@Module({
  imports: [TypeOrmModule.forFeature([User])],
  controllers: [UsersController],
  providers: [UsersService],
  exports: [UsersService],
})
export class UsersModule {}

// users.controller.ts
@Controller("users")
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  @UseGuards(AuthGuard)
  findAll(@Query() query: PaginationDto): Promise<User[]> {
    return this.usersService.findAll(query);
  }

  @Post()
  @UsePipes(new ValidationPipe({ whitelist: true }))
  create(@Body() dto: CreateUserDto): Promise<User> {
    return this.usersService.create(dto);
  }
}
```

## Validation with Zod

Zod provides runtime type-safe validation:

```typescript
import { z } from "zod";

const CreateUserSchema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().int().positive().optional(),
  role: z.enum(["admin", "user", "viewer"]).default("user"),
});

type CreateUser = z.infer<typeof CreateUserSchema>;

// Express middleware
function validate<T>(schema: z.ZodType<T>) {
  return (req: Request, res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      return res.status(400).json({ errors: result.error.flatten().fieldErrors });
    }
    req.body = result.data;
    next();
  };
}

app.post("/users", validate(CreateUserSchema), createUserHandler);
```

## Error Handling Patterns

Consistent error handling across frameworks:

```typescript
// Custom error hierarchy
class AppError extends Error {
  constructor(
    message: string,
    public statusCode: number = 500,
    public code: string = "INTERNAL_ERROR",
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}

class NotFoundError extends AppError {
  constructor(resource: string, id: string) {
    super(`${resource} with id '${id}' not found`, 404, "NOT_FOUND");
  }
}

// Result pattern (no exceptions for expected failures)
type Result<T, E = AppError> =
  | { success: true; data: T }
  | { success: false; error: E };
```

## Rate Limiting

```typescript
import rateLimit from "express-rate-limit";

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => req.ip ?? "unknown",
});

app.use("/api/", limiter);
```
