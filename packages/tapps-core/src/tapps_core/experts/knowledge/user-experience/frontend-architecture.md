# Frontend Architecture & React Patterns

## Overview

Frontend architecture in 2026 centers on React Server Components, framework-level optimizations (Next.js, Remix, Astro), and a shift toward server-first rendering with selective client interactivity. This guide covers the dominant architectural patterns, component design, and state management approaches.

## React Component Patterns (2026)

### Server Components vs. Client Components

React Server Components (RSC) run on the server, sending only HTML to the client. Client Components run in the browser and handle interactivity.

```tsx
// Server Component (default in Next.js App Router)
// Can: fetch data, access backend, read files, use async/await
// Cannot: use hooks, add event handlers, use browser APIs
async function ProductPage({ params }) {
  const product = await db.products.findById(params.id);

  return (
    <main>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <ProductPrice price={product.price} />

      {/* Client Component for interactivity */}
      <AddToCartButton productId={product.id} />
    </main>
  );
}
```

```tsx
// Client Component — must opt in with 'use client'
'use client';

import { useState } from 'react';

function AddToCartButton({ productId }) {
  const [adding, setAdding] = useState(false);

  async function handleClick() {
    setAdding(true);
    await addToCart(productId);
    setAdding(false);
  }

  return (
    <button onClick={handleClick} disabled={adding}>
      {adding ? 'Adding...' : 'Add to Cart'}
    </button>
  );
}
```

**Decision framework:**
- Default to Server Components
- Use Client Components only when you need: hooks, event handlers, browser APIs, or third-party client libraries
- Keep Client Components as small and leaf-level as possible

### Server Actions

```tsx
// Server Action — runs on the server, called from client
async function submitOrder(formData: FormData) {
  'use server';

  const items = JSON.parse(formData.get('items') as string);
  const order = await db.orders.create({ items });
  redirect(`/orders/${order.id}`);
}

// Used in a form (works without JavaScript)
function CheckoutForm({ items }) {
  return (
    <form action={submitOrder}>
      <input type="hidden" name="items" value={JSON.stringify(items)} />
      <button type="submit">Place Order</button>
    </form>
  );
}
```

### Composition Over Inheritance

```tsx
// Pattern: Slots via children and render props
function Card({ children, header, footer }) {
  return (
    <div className="card">
      {header && <div className="card-header">{header}</div>}
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}

// Usage
<Card
  header={<h3>Product Name</h3>}
  footer={<Button>Buy Now</Button>}
>
  <p>Product description here.</p>
</Card>
```

### Polymorphic Components

```tsx
// Component that renders as different HTML elements
type PolymorphicProps<T extends React.ElementType> = {
  as?: T;
  children: React.ReactNode;
} & React.ComponentPropsWithoutRef<T>;

function Text<T extends React.ElementType = 'p'>({
  as,
  children,
  ...props
}: PolymorphicProps<T>) {
  const Component = as || 'p';
  return <Component {...props}>{children}</Component>;
}

// Usage
<Text>Default paragraph</Text>
<Text as="span">Inline text</Text>
<Text as="h2" className="title">Heading</Text>
<Text as="label" htmlFor="email">Email</Text>
```

## State Management

### When to Use What

| Scope | Solution | Example |
|-------|----------|---------|
| Component-local | `useState` | Form inputs, toggles, UI state |
| Derived/computed | `useMemo` | Filtered lists, calculations |
| Shared (small) | Context + `useReducer` | Theme, auth, locale |
| Shared (complex) | Zustand / Jotai | Shopping cart, notifications |
| Server state | React Query / SWR | API data, caching, revalidation |
| URL state | Search params | Filters, pagination, sort |
| Form state | React Hook Form | Complex forms with validation |

### React Query for Server State

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

function ProductList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['products'],
    queryFn: () => fetch('/api/products').then(r => r.json()),
    staleTime: 5 * 60 * 1000, // Fresh for 5 minutes
  });

  if (isLoading) return <ProductListSkeleton />;
  if (error) return <ErrorState error={error} />;

  return (
    <ul>
      {data.map(product => (
        <ProductCard key={product.id} product={product} />
      ))}
    </ul>
  );
}

// Mutation with optimistic update
function useDeleteProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => fetch(`/api/products/${id}`, { method: 'DELETE' }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['products'] });
      const previous = queryClient.getQueryData(['products']);
      queryClient.setQueryData(['products'], (old) =>
        old.filter(p => p.id !== id)
      );
      return { previous };
    },
    onError: (err, id, context) => {
      queryClient.setQueryData(['products'], context.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });
}
```

### Zustand for Client State

```tsx
import { create } from 'zustand';

interface CartStore {
  items: CartItem[];
  addItem: (product: Product) => void;
  removeItem: (id: string) => void;
  total: () => number;
}

const useCart = create<CartStore>((set, get) => ({
  items: [],
  addItem: (product) =>
    set((state) => ({
      items: [...state.items, { ...product, quantity: 1 }],
    })),
  removeItem: (id) =>
    set((state) => ({
      items: state.items.filter((item) => item.id !== id),
    })),
  total: () =>
    get().items.reduce((sum, item) => sum + item.price * item.quantity, 0),
}));
```

### URL State for Filters/Pagination

```tsx
import { useSearchParams } from 'next/navigation';

function ProductFilters() {
  const searchParams = useSearchParams();
  const category = searchParams.get('category') || 'all';
  const sort = searchParams.get('sort') || 'newest';
  const page = parseInt(searchParams.get('page') || '1');

  function updateFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams);
    params.set(key, value);
    params.set('page', '1'); // Reset page on filter change
    router.push(`?${params.toString()}`);
  }

  return (
    <div className="filters">
      <select value={category} onChange={e => updateFilter('category', e.target.value)}>
        <option value="all">All Categories</option>
        <option value="electronics">Electronics</option>
        <option value="clothing">Clothing</option>
      </select>
    </div>
  );
}
```

## File & Folder Structure

### Feature-Based Organization

```
src/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx
│   ├── page.tsx
│   ├── products/
│   │   ├── page.tsx
│   │   ├── [id]/
│   │   │   └── page.tsx
│   │   └── loading.tsx
│   └── cart/
│       └── page.tsx
├── components/
│   ├── ui/                 # Reusable design system components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   └── input.tsx
│   └── features/           # Feature-specific components
│       ├── products/
│       │   ├── product-card.tsx
│       │   ├── product-list.tsx
│       │   └── product-filters.tsx
│       └── cart/
│           ├── cart-item.tsx
│           └── cart-summary.tsx
├── hooks/                  # Custom hooks
│   ├── use-cart.ts
│   └── use-debounce.ts
├── lib/                    # Utilities, API clients
│   ├── api.ts
│   ├── utils.ts
│   └── constants.ts
├── stores/                 # State management
│   └── cart-store.ts
└── types/                  # TypeScript types
    └── product.ts
```

### Naming Conventions

- **Components**: PascalCase (`ProductCard.tsx` or `product-card.tsx`)
- **Hooks**: camelCase with `use` prefix (`useCart.ts`)
- **Utilities**: camelCase (`formatCurrency.ts`)
- **Types**: PascalCase (`Product`, `CartItem`)
- **Constants**: SCREAMING_SNAKE_CASE (`MAX_CART_ITEMS`)
- **CSS Modules**: kebab-case matching component (`product-card.module.css`)

## Error Handling

### Error Boundaries

```tsx
'use client';

function ErrorBoundary({ children, fallback }) {
  return (
    <ErrorBoundaryInner fallback={fallback}>
      {children}
    </ErrorBoundaryInner>
  );
}

// Usage: isolate errors to specific UI sections
<ErrorBoundary fallback={<ProductError />}>
  <ProductRecommendations />
</ErrorBoundary>
```

### Next.js Error Files

```tsx
// app/products/error.tsx — catches errors in this route segment
'use client';

export default function ProductsError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div role="alert" className="error-state">
      <h2>Something went wrong loading products</h2>
      <p>{error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

## Performance Patterns

### Code Splitting

```tsx
import { lazy, Suspense } from 'react';

// Lazy-load heavy components
const Chart = lazy(() => import('./Chart'));
const RichTextEditor = lazy(() => import('./RichTextEditor'));

function Dashboard() {
  return (
    <div>
      <Suspense fallback={<ChartSkeleton />}>
        <Chart data={data} />
      </Suspense>
    </div>
  );
}
```

### Memoization

```tsx
// Memo: prevent re-renders when props haven't changed
const ProductCard = memo(function ProductCard({ product }) {
  return (
    <div className="card">
      <h3>{product.name}</h3>
      <p>{product.price}</p>
    </div>
  );
});

// useMemo: expensive computations
const sortedProducts = useMemo(
  () => products.sort((a, b) => a.price - b.price),
  [products]
);

// useCallback: stable function references for child components
const handleSort = useCallback((key: string) => {
  setSortKey(key);
}, []);
```

**Don't over-memoize.** Only memo when:
- Component re-renders often with same props
- Component is expensive to render
- Component is passed as prop to memoized children

## Framework Choices (2026)

| Framework | Best For |
|-----------|----------|
| **Next.js** | Full-stack React apps, SSR/SSG, API routes |
| **Remix** | Data-heavy apps, progressive enhancement |
| **Astro** | Content sites, docs, blogs (islands architecture) |
| **Vite + React** | SPAs, internal tools, no SSR needed |
| **React Native** | Mobile apps sharing logic with web |

## Common Mistakes

### Prop Drilling

- Problem: Passing props through 4+ component levels
- Fix: Use Context, Zustand, or component composition (render props, slots)

### useEffect for Data Fetching

- Problem: `useEffect` + `fetch` causes waterfalls, race conditions, no caching
- Fix: Use React Query, SWR, or Server Components for data fetching

### Giant Components

- Problem: 300+ line components doing everything
- Fix: Extract custom hooks for logic, break UI into smaller components

### Client Components Everywhere

- Problem: Adding 'use client' to every file — ships unnecessary JavaScript
- Fix: Default to Server Components; only add 'use client' where interactivity is needed

### Not Handling Loading and Error States

- Problem: Components assume data is always available
- Fix: Every async operation needs loading, error, and empty states
