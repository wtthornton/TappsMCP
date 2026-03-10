# Performance UX

## Overview

Performance is a UX feature. Users abandon pages that take more than 3 seconds to load, and perceive applications as sluggish when interactions take more than 100ms to respond. Performance UX focuses on both actual speed and perceived speed — making applications feel fast even when operations take time.

## Core Web Vitals (2026)

Google's Core Web Vitals are the standard performance metrics affecting search ranking and user experience.

### Largest Contentful Paint (LCP)

Measures loading performance — when the largest visible element finishes rendering.

| Rating | Threshold |
|--------|-----------|
| Good | ≤ 2.5s |
| Needs Improvement | 2.5s – 4.0s |
| Poor | > 4.0s |

**Optimization strategies:**
- Preload critical resources: `<link rel="preload" as="image" href="hero.webp">`
- Use responsive images: `srcset` and `sizes` attributes
- Optimize server response time (TTFB < 800ms)
- Use CDN for static assets
- Implement font preloading with `font-display: swap`
- Avoid lazy-loading above-the-fold images

```html
<!-- Hero image: eager load, preload, fetchpriority high -->
<img
  src="hero.webp"
  alt="Product hero"
  fetchpriority="high"
  loading="eager"
  decoding="async"
  width="1200"
  height="600"
/>

<!-- Below-fold images: lazy load -->
<img
  src="feature.webp"
  alt="Feature screenshot"
  loading="lazy"
  decoding="async"
  width="600"
  height="400"
/>
```

### Interaction to Next Paint (INP)

Measures responsiveness — the delay between user interaction and visual response.

| Rating | Threshold |
|--------|-----------|
| Good | ≤ 200ms |
| Needs Improvement | 200ms – 500ms |
| Poor | > 500ms |

**Optimization strategies:**
- Break long tasks with `scheduler.yield()` or `requestIdleCallback`
- Defer non-critical JavaScript
- Use web workers for heavy computation
- Minimize main thread work during interactions
- Avoid layout thrashing (batch DOM reads/writes)

```javascript
// Break long tasks to stay responsive
async function processLargeList(items) {
  for (const chunk of chunkArray(items, 50)) {
    processChunk(chunk);
    // Yield to browser between chunks
    await scheduler.yield();
  }
}

// Or use requestIdleCallback for non-urgent work
requestIdleCallback((deadline) => {
  while (deadline.timeRemaining() > 5 && tasks.length > 0) {
    processTask(tasks.shift());
  }
});
```

### Cumulative Layout Shift (CLS)

Measures visual stability — unexpected layout shifts during page life.

| Rating | Threshold |
|--------|-----------|
| Good | ≤ 0.1 |
| Needs Improvement | 0.1 – 0.25 |
| Poor | > 0.25 |

**Optimization strategies:**
- Always set width/height or aspect-ratio on images and videos
- Reserve space for dynamic content (ads, embeds)
- Use CSS `contain` for isolated components
- Avoid inserting content above existing content
- Use `content-visibility: auto` for off-screen content

```css
/* Reserve space for images */
img {
  aspect-ratio: attr(width) / attr(height);
  width: 100%;
  height: auto;
}

/* Reserve space for dynamic embeds */
.embed-container {
  aspect-ratio: 16 / 9;
  contain: layout;
}
```

## Skeleton Screens

Show placeholder shapes that match the layout of incoming content — significantly better perceived performance than spinners.

```css
/* Skeleton loading animation */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-skeleton) 25%,
    var(--color-skeleton-highlight) 50%,
    var(--color-skeleton) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
  border-radius: 4px;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Match real content dimensions */
.skeleton-title {
  height: 1.5rem;
  width: 60%;
  margin-bottom: 0.75rem;
}

.skeleton-text {
  height: 1rem;
  width: 100%;
  margin-bottom: 0.5rem;
}

.skeleton-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
}
```

```tsx
// React skeleton component
function CardSkeleton() {
  return (
    <div className="card" aria-busy="true" aria-label="Loading content">
      <div className="skeleton skeleton-avatar" />
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-text" />
      <div className="skeleton skeleton-text" style={{ width: '80%' }} />
    </div>
  );
}

function CardList({ data, isLoading }) {
  if (isLoading) {
    return Array.from({ length: 6 }, (_, i) => <CardSkeleton key={i} />);
  }
  return data.map(item => <Card key={item.id} {...item} />);
}
```

## Optimistic UI

Update the UI immediately before server confirmation, then reconcile.

```tsx
function LikeButton({ postId, initialLiked, initialCount }) {
  const [liked, setLiked] = useState(initialLiked);
  const [count, setCount] = useState(initialCount);

  async function handleLike() {
    // Optimistic update
    const newLiked = !liked;
    setLiked(newLiked);
    setCount(c => newLiked ? c + 1 : c - 1);

    try {
      await api.toggleLike(postId);
    } catch {
      // Revert on failure
      setLiked(!newLiked);
      setCount(c => newLiked ? c - 1 : c + 1);
      toast.error('Failed to update. Please try again.');
    }
  }

  return (
    <button onClick={handleLike} aria-pressed={liked}>
      {liked ? '❤️' : '🤍'} {count}
    </button>
  );
}
```

### When to Use Optimistic UI

- **Good candidates**: Likes, bookmarks, toggles, text edits, reordering
- **Bad candidates**: Payments, deletions, irreversible actions, multi-step forms

## Streaming & Suspense

### React Server Components + Streaming

```tsx
// Layout streams immediately, slow content streams in later
export default function ProductPage({ params }) {
  return (
    <main>
      <ProductHeader id={params.id} />

      <Suspense fallback={<ReviewsSkeleton />}>
        <ProductReviews id={params.id} />
      </Suspense>

      <Suspense fallback={<RecommendationsSkeleton />}>
        <Recommendations id={params.id} />
      </Suspense>
    </main>
  );
}
```

### Progressive Loading

Load content in priority order:

1. **Critical**: Navigation, page heading, primary content
2. **High**: Key images, interactive elements
3. **Medium**: Secondary content, related items
4. **Low**: Analytics, ads, comments, recommendations

```html
<!-- Critical CSS inline -->
<style>/* above-the-fold styles */</style>

<!-- Deferred non-critical CSS -->
<link rel="preload" href="below-fold.css" as="style" onload="this.onload=null;this.rel='stylesheet'">

<!-- Defer non-critical JS -->
<script src="analytics.js" defer></script>
<script src="chat-widget.js" type="module" async></script>
```

## Loading States

### The Loading State Hierarchy

1. **Instant** (< 100ms): No indicator needed
2. **Brief** (100ms – 1s): Subtle indicator (opacity change, skeleton)
3. **Medium** (1s – 5s): Progress indicator, skeleton screen
4. **Long** (5s+): Progress bar with estimate, ability to background the task

```tsx
function SubmitButton({ isSubmitting }) {
  return (
    <button type="submit" disabled={isSubmitting}>
      {isSubmitting ? (
        <>
          <Spinner size="sm" aria-hidden="true" />
          <span>Saving...</span>
        </>
      ) : (
        'Save Changes'
      )}
    </button>
  );
}
```

### Avoiding Loading Spinners

Spinners are a last resort. Prefer:
- **Skeleton screens** for initial page loads
- **Optimistic UI** for user actions
- **Inline indicators** for form submissions
- **Progress bars** for file uploads and long operations
- **Background processing** for non-blocking tasks

## Image Optimization

```html
<!-- Modern image loading pattern -->
<picture>
  <!-- AVIF: best compression (supported Chrome, Firefox) -->
  <source type="image/avif" srcset="photo.avif" />
  <!-- WebP: good compression (universal support) -->
  <source type="image/webp" srcset="photo.webp" />
  <!-- Fallback -->
  <img src="photo.jpg" alt="Description" width="800" height="600"
       loading="lazy" decoding="async" />
</picture>

<!-- Responsive images -->
<img
  srcset="photo-400.webp 400w, photo-800.webp 800w, photo-1200.webp 1200w"
  sizes="(max-width: 600px) 100vw, (max-width: 1200px) 50vw, 33vw"
  src="photo-800.webp"
  alt="Description"
  loading="lazy"
/>
```

## Font Loading

```css
/* Prevent layout shift from font loading */
@font-face {
  font-family: 'Inter';
  src: url('inter-var.woff2') format('woff2');
  font-weight: 100 900;
  font-display: swap; /* Show fallback immediately, swap when loaded */
  unicode-range: U+0000-00FF; /* Latin only — reduces download */
}

/* Size-adjust fallback to minimize CLS */
@font-face {
  font-family: 'Inter Fallback';
  src: local('Arial');
  size-adjust: 107%;
  ascent-override: 90%;
  descent-override: 22%;
  line-gap-override: 0%;
}

body {
  font-family: 'Inter', 'Inter Fallback', system-ui, sans-serif;
}
```

## Common Mistakes

### Loading Everything Upfront

- Problem: Bundle includes code for every route and feature
- Fix: Code-split by route, lazy-load non-critical features

### Blocking Render with Third-Party Scripts

- Problem: Analytics, chat widgets, A/B testing block page render
- Fix: Load all third-party scripts with `async` or `defer`, use Partytown for web workers

### Ignoring Mobile Performance

- Problem: Testing only on fast desktop connections
- Fix: Test on throttled 3G/4G, use Performance panel in DevTools with CPU throttling

### Layout Shift from Dynamic Content

- Problem: Content injected after render pushes visible elements
- Fix: Reserve space with CSS, use `min-height`, announce changes to screen readers
