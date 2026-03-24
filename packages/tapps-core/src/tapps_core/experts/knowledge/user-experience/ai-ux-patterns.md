# AI UX Patterns

## Overview

See also: **prompt-first AI governance** (`prompt-first-ai-feature-governance.md`), **dual-surface admin + SPA** (`dual-surface-admin-spa-operational-ui.md`), and **semantic dashboard UI** (`semantic-status-dashboard-ui.md`) for operational consoles and fleet-style dashboards.

AI-powered interfaces are now mainstream. From chat assistants to inline copilots, generative search to smart suggestions — designing effective AI UX requires new patterns for trust, transparency, control, and error recovery. This guide covers the dominant AI UX patterns of 2025-2026.

## Core Principles for AI UX

### Transparency

Users must understand when they're interacting with AI and what it can/can't do.

- **Label AI-generated content** clearly ("AI-generated", "Suggested by AI")
- **Show confidence levels** when appropriate (high/medium/low, not raw percentages)
- **Explain limitations** upfront ("I can help with X, but not Y")
- **Disclose data usage** ("Your inputs may be used to improve the model")

### User Control

Users must remain in charge. AI assists; users decide.

- **Always editable**: AI output should be a starting point, not final
- **Easy to dismiss**: One click to reject suggestions
- **Undo/revert**: Return to pre-AI state at any time
- **Adjustable intensity**: Let users control how proactive AI is (off / subtle / active)

### Graceful Failure

AI will be wrong. Design for it.

- **Never present AI output as fact** without allowing verification
- **Provide sources** and citations where possible
- **Design clear error states** for AI failures (timeout, no results, low confidence)
- **Feedback mechanisms**: Let users flag incorrect AI output

## Conversational UI Patterns

### Chat Interface

```html
<div class="chat-container" role="log" aria-live="polite" aria-label="Chat with AI assistant">
  <!-- Message from user -->
  <div class="message user" role="article">
    <div class="message-content">How do I center a div?</div>
  </div>

  <!-- Message from AI -->
  <div class="message assistant" role="article">
    <div class="message-meta">
      <span class="ai-badge" aria-label="AI-generated response">AI</span>
    </div>
    <div class="message-content">
      <!-- Rendered markdown content -->
    </div>
    <div class="message-actions">
      <button aria-label="Copy response">Copy</button>
      <button aria-label="Rate as helpful">👍</button>
      <button aria-label="Rate as unhelpful">👎</button>
    </div>
  </div>
</div>
```

### Streaming Responses

Show AI responses as they generate — critical for perceived speed.

```tsx
function StreamingMessage({ stream }) {
  const [content, setContent] = useState('');
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const reader = stream.getReader();
    async function read() {
      while (true) {
        const { done, value } = await reader.read();
        if (done) { setIsComplete(true); break; }
        setContent(prev => prev + value);
      }
    }
    read();
  }, [stream]);

  return (
    <div className="message assistant" aria-busy={!isComplete}>
      <Markdown>{content}</Markdown>
      {!isComplete && <TypingIndicator />}
      {isComplete && <MessageActions />}
    </div>
  );
}
```

### Suggested Prompts

Guide users who don't know what to ask:

```tsx
function SuggestedPrompts({ onSelect }) {
  const suggestions = [
    { icon: '✏️', text: 'Help me write a product description' },
    { icon: '📊', text: 'Analyze this data for trends' },
    { icon: '🔍', text: 'Explain this error message' },
    { icon: '💡', text: 'Suggest improvements for my code' },
  ];

  return (
    <div className="suggestions" role="list" aria-label="Suggested prompts">
      {suggestions.map(s => (
        <button key={s.text} onClick={() => onSelect(s.text)} role="listitem">
          <span aria-hidden="true">{s.icon}</span>
          {s.text}
        </button>
      ))}
    </div>
  );
}
```

## Inline AI Assistance

### Copilot Pattern

AI suggestions appear inline in the user's workflow — accept, modify, or dismiss.

```css
/* Ghost text suggestion (like GitHub Copilot) */
.suggestion-ghost {
  color: var(--color-text-muted);
  opacity: 0.5;
  font-style: italic;
  pointer-events: none;
}

/* Inline suggestion banner */
.suggestion-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--color-ai-bg);
  border-left: 3px solid var(--color-ai-accent);
  border-radius: 0 4px 4px 0;
}
```

Key UX requirements:
- **Tab to accept** — fastest path for accepting suggestions
- **Escape to dismiss** — clear, immediate rejection
- **Partial acceptance** — accept word-by-word or line-by-line
- **No blocking** — suggestions never prevent normal typing
- **Debounced** — don't suggest on every keystroke (300-500ms delay)

### Smart Suggestions

Context-aware suggestions in forms, search, and editors:

```tsx
function SmartInput({ onSubmit, getSuggestions }) {
  const [value, setValue] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);

  // Debounced suggestion fetching
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (value.length >= 2) {
        const results = await getSuggestions(value);
        setSuggestions(results);
      } else {
        setSuggestions([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [value]);

  return (
    <div className="smart-input" role="combobox" aria-expanded={suggestions.length > 0}>
      <input
        value={value}
        onChange={e => setValue(e.target.value)}
        aria-autocomplete="list"
        aria-controls="suggestion-list"
        aria-activedescendant={selectedIndex >= 0 ? `suggestion-${selectedIndex}` : undefined}
      />
      {suggestions.length > 0 && (
        <ul role="listbox" id="suggestion-list">
          {suggestions.map((s, i) => (
            <li
              key={s.id}
              id={`suggestion-${i}`}
              role="option"
              aria-selected={i === selectedIndex}
              onClick={() => onSubmit(s.value)}
            >
              <span className="suggestion-text">{s.label}</span>
              <span className="ai-badge">AI</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

## Generative UI Patterns

### AI-Generated Content Cards

```tsx
function AIContentCard({ content, sources, confidence }) {
  return (
    <div className="ai-card">
      <div className="ai-card-header">
        <span className="ai-badge">AI Generated</span>
        {confidence === 'low' && (
          <span className="confidence-warning" role="alert">
            Low confidence — verify this information
          </span>
        )}
      </div>

      <div className="ai-card-body">
        <Markdown>{content}</Markdown>
      </div>

      {sources?.length > 0 && (
        <div className="ai-card-sources">
          <h4>Sources</h4>
          <ul>
            {sources.map(s => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener">{s.title}</a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ai-card-actions">
        <button>Edit</button>
        <button>Regenerate</button>
        <button>Copy</button>
        <FeedbackButtons />
      </div>
    </div>
  );
}
```

### AI Search / Retrieval Augmented Generation (RAG)

```tsx
function AISearchResults({ query, results }) {
  return (
    <div className="search-results">
      {/* AI summary at top */}
      <div className="ai-summary">
        <div className="ai-badge">AI Overview</div>
        <Markdown>{results.summary}</Markdown>
        <details>
          <summary>{results.sources.length} sources referenced</summary>
          <SourceList sources={results.sources} />
        </details>
      </div>

      {/* Traditional results below */}
      <h2>All results</h2>
      {results.items.map(item => (
        <SearchResult key={item.id} {...item} />
      ))}
    </div>
  );
}
```

## Loading & Progress for AI

### Thinking Indicators

AI responses take longer than database queries. Communicate progress:

```tsx
function AIThinkingState({ stage }) {
  const stages = [
    { key: 'analyzing', label: 'Analyzing your request...' },
    { key: 'searching', label: 'Searching knowledge base...' },
    { key: 'generating', label: 'Generating response...' },
  ];

  return (
    <div className="thinking-state" role="status" aria-live="polite">
      {stages.map(s => (
        <div
          key={s.key}
          className={`stage ${s.key === stage ? 'active' : s.key < stage ? 'done' : ''}`}
        >
          {s.key === stage ? <Spinner /> : s.key < stage ? '✓' : '○'}
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}
```

### Cancellation

Always allow users to cancel AI operations:

```tsx
function AIChat() {
  const [abortController, setAbortController] = useState(null);

  async function sendMessage(prompt) {
    const controller = new AbortController();
    setAbortController(controller);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ prompt }),
        signal: controller.signal,
      });
      // Handle streaming response...
    } catch (err) {
      if (err.name === 'AbortError') {
        // User cancelled — show partial result or clean state
      }
    } finally {
      setAbortController(null);
    }
  }

  return (
    <>
      {abortController && (
        <button onClick={() => abortController.abort()}>
          Stop generating
        </button>
      )}
    </>
  );
}
```

## Trust & Safety

### Content Warnings

```tsx
function AIResponse({ content, flags }) {
  if (flags?.includes('potentially_harmful')) {
    return (
      <div className="content-warning" role="alert">
        <h3>Content Warning</h3>
        <p>This AI response may contain inaccurate or sensitive information.</p>
        <button onClick={() => setShowContent(true)}>Show anyway</button>
      </div>
    );
  }
  return <Markdown>{content}</Markdown>;
}
```

### Feedback Loop

Every AI interaction should have a feedback mechanism:

- **Binary**: 👍/👎 for quick signal
- **Categorical**: "Incorrect", "Not helpful", "Offensive", "Outdated"
- **Open-ended**: "What went wrong?" text field for detailed feedback
- **Implicit**: Track if user edits, copies, or ignores AI output

## Prompt Design for Users

### Prompt Templates

Help users write effective prompts:

```tsx
function PromptBuilder({ onSubmit }) {
  return (
    <form onSubmit={onSubmit}>
      <label>I want to:</label>
      <select name="action">
        <option value="write">Write</option>
        <option value="edit">Edit</option>
        <option value="analyze">Analyze</option>
        <option value="explain">Explain</option>
      </select>

      <label>About:</label>
      <textarea name="topic" placeholder="Describe what you need..." />

      <label>Tone:</label>
      <select name="tone">
        <option value="professional">Professional</option>
        <option value="casual">Casual</option>
        <option value="technical">Technical</option>
      </select>

      <button type="submit">Generate</button>
    </form>
  );
}
```

## Real-World AI UX References

### Vercel v0 — Generative UI

v0 by Vercel represents the cutting edge of AI-to-UI workflows:
- Users describe a UI in natural language, v0 generates React + Tailwind code
- Iterative refinement — "make the header sticky", "add dark mode"
- Generated code uses shadcn/ui components (production-ready, accessible)
- Preview renders live alongside the code
- Key UX insight: show the result AND the code — let users learn and customize

### Linear — AI as Invisible Assistant

Linear integrates AI without making it the centerpiece:
- Auto-categorization of issues based on content
- Smart suggestions for project assignment and priority
- AI summarization of long threads
- Key UX insight: best AI features feel like the product is just smarter, not that there's an AI bolted on

### Figma AI — Design Tool Integration

Figma's AI features enhance the design workflow:
- "Make a design" generates layouts from text descriptions
- Auto-rename layers based on content
- Smart suggestions for design tokens and component usage
- Key UX insight: AI works best when it reduces tedious tasks, not when it replaces creative decisions

### GitHub Copilot — Inline Code Assistance

The most widely adopted AI coding assistant:
- Ghost text suggestions that appear inline (non-blocking)
- Tab to accept, Escape to dismiss, Cmd+→ for word-by-word
- Context-aware — reads open files, recent edits, project structure
- Key UX insight: suggestions must never interrupt flow — they should be discoverable but ignorable

## Common Mistakes

### No Loading State for AI

- Problem: User clicks, nothing happens for 3-5 seconds
- Fix: Immediate visual feedback, streaming responses, thinking indicators

### AI Output Without Attribution

- Problem: Can't tell what's AI-generated vs. human-written
- Fix: Clear AI badges, source citations, confidence indicators

### No Way to Recover from Bad AI Output

- Problem: AI generates wrong content, user has no recourse
- Fix: Edit, regenerate, undo buttons on every AI output; revert to original

### Treating AI as Infallible

- Problem: Presenting AI output as definitive answers
- Fix: Use language like "suggested", "based on available information", show confidence levels

### Over-Automating

- Problem: AI takes actions without user consent
- Fix: Always preview before applying; "Apply" button, not auto-apply; show diff of changes
