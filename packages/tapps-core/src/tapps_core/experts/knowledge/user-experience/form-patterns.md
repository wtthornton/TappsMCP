# Form UX Patterns

## Overview

Forms are where users transact — sign up, check out, submit data, configure settings. Poor form UX is the #1 cause of abandonment and user frustration. This guide covers modern form patterns that reduce friction, prevent errors, and work for everyone.

## Core Form Principles

1. **Ask only what you need** — Every field is friction. Remove unnecessary fields.
2. **One column layout** — Multi-column forms are slower to complete and harder to scan.
3. **Top-aligned labels** — Fastest eye-tracking pattern (left-aligned for long forms).
4. **Smart defaults** — Pre-fill when possible (location, date, preferences).
5. **Progressive disclosure** — Show fields only when relevant.
6. **Inline validation** — Validate on blur, not on every keystroke.

## Label & Input Patterns

### Label Placement

```html
<!-- Top-aligned labels (recommended for most forms) -->
<div class="form-group">
  <label for="email">Email address</label>
  <input type="email" id="email" name="email" autocomplete="email" />
</div>

<!-- Floating labels (space-efficient, but worse for accessibility) -->
<div class="form-group floating">
  <input type="email" id="email" name="email" placeholder=" " autocomplete="email" />
  <label for="email">Email address</label>
</div>
```

```css
/* Floating label pattern */
.form-group.floating {
  position: relative;
}

.form-group.floating input {
  padding: 1.25rem 0.75rem 0.5rem;
}

.form-group.floating label {
  position: absolute;
  top: 50%;
  left: 0.75rem;
  transform: translateY(-50%);
  transition: all 150ms ease;
  color: var(--color-text-tertiary);
  pointer-events: none;
}

.form-group.floating input:focus + label,
.form-group.floating input:not(:placeholder-shown) + label {
  top: 0.5rem;
  transform: translateY(0);
  font-size: 0.75rem;
  color: var(--color-primary);
}
```

### Required Fields

```html
<!-- Mark required fields clearly -->
<label for="name">
  Full name <span class="required" aria-hidden="true">*</span>
</label>
<input type="text" id="name" required aria-required="true" autocomplete="name" />

<!-- Or mark optional fields (better when most fields are required) -->
<label for="phone">
  Phone number <span class="optional">(optional)</span>
</label>
<input type="tel" id="phone" autocomplete="tel" />
```

### Help Text

```html
<div class="form-group">
  <label for="password">Password</label>
  <input
    type="password"
    id="password"
    aria-describedby="password-help"
    autocomplete="new-password"
  />
  <p id="password-help" class="help-text">
    At least 8 characters with one number and one special character.
  </p>
</div>
```

## Validation

### Inline Validation (On Blur)

```tsx
function FormField({ name, label, validate, ...props }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [touched, setTouched] = useState(false);

  function handleBlur() {
    setTouched(true);
    const err = validate(value);
    setError(err || '');
  }

  return (
    <div className={`form-group ${touched && error ? 'has-error' : ''}`}>
      <label htmlFor={name}>{label}</label>
      <input
        id={name}
        name={name}
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={handleBlur}
        aria-invalid={touched && !!error}
        aria-describedby={error ? `${name}-error` : undefined}
        {...props}
      />
      {touched && error && (
        <p id={`${name}-error`} className="error-text" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
```

### Validation Timing

| When | Pattern | Example |
|------|---------|---------|
| **On blur** | Validate when user leaves field | Email format check |
| **On change (after error)** | Clear error as user corrects | Remove "required" error as they type |
| **On submit** | Catch all remaining errors | Server-side validation |
| **Never on first keystroke** | Don't show errors before user finishes | Password strength |

### Error Messages

```css
.error-text {
  color: var(--color-error);
  font-size: 0.875rem;
  margin-top: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.error-text::before {
  content: '';
  display: inline-block;
  width: 16px;
  height: 16px;
  background: url('error-icon.svg') no-repeat;
}

/* Error state on input */
.form-group.has-error input {
  border-color: var(--color-error);
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
}
```

**Good error messages:**
- "Please enter a valid email address" (not "Invalid input")
- "Password must be at least 8 characters" (not "Too short")
- "This email is already registered. Sign in instead?" (not "Duplicate")

### Error Summary

For complex forms, show a summary at the top on submit:

```html
<div role="alert" class="error-summary" tabindex="-1">
  <h2>Please fix the following errors:</h2>
  <ul>
    <li><a href="#email">Email address is required</a></li>
    <li><a href="#password">Password must be at least 8 characters</a></li>
  </ul>
</div>
```

Focus the error summary on submit so screen readers announce it.

## Multi-Step Forms

### Stepper Pattern

```html
<nav aria-label="Form progress">
  <ol class="stepper" role="list">
    <li class="step completed" aria-current="false">
      <span class="step-number">1</span>
      <span class="step-label">Account</span>
    </li>
    <li class="step active" aria-current="step">
      <span class="step-number">2</span>
      <span class="step-label">Profile</span>
    </li>
    <li class="step" aria-current="false">
      <span class="step-number">3</span>
      <span class="step-label">Preferences</span>
    </li>
  </ol>
</nav>
```

### Multi-Step Best Practices

- **Show progress** — Step indicator with total count ("Step 2 of 4")
- **Allow back navigation** — Users should review/edit previous steps
- **Preserve state** — Don't lose data when navigating between steps
- **Validate per step** — Don't let users advance with errors
- **Summary before submit** — Review all entered data on final step
- **Save drafts** — Auto-save for long forms (with user notification)

## Input Types & Autocomplete

### HTML5 Input Types

Use the right input type — it triggers the correct mobile keyboard and enables browser autofill:

```html
<input type="email" autocomplete="email" />
<input type="tel" autocomplete="tel" />
<input type="url" autocomplete="url" />
<input type="number" inputmode="numeric" />
<input type="search" />
<input type="date" />
<input type="time" />
<input type="password" autocomplete="current-password" />
<input type="password" autocomplete="new-password" />
```

### Autocomplete Attributes

```html
<!-- Personal info -->
<input autocomplete="given-name" />  <!-- First name -->
<input autocomplete="family-name" /> <!-- Last name -->
<input autocomplete="email" />
<input autocomplete="tel" />
<input autocomplete="bday" />        <!-- Birthday -->

<!-- Address -->
<input autocomplete="street-address" />
<input autocomplete="address-level2" />  <!-- City -->
<input autocomplete="address-level1" />  <!-- State/Province -->
<input autocomplete="postal-code" />
<input autocomplete="country" />

<!-- Payment -->
<input autocomplete="cc-name" />
<input autocomplete="cc-number" />
<input autocomplete="cc-exp" />
<input autocomplete="cc-csc" />

<!-- Login -->
<input autocomplete="username" />
<input autocomplete="current-password" />
<input autocomplete="new-password" />
<input autocomplete="one-time-code" />  <!-- OTP/2FA -->
```

## Specialized Input Patterns

### Password Fields

```html
<div class="form-group">
  <label for="password">Password</label>
  <div class="input-with-action">
    <input
      type="password"
      id="password"
      autocomplete="new-password"
      aria-describedby="password-requirements"
    />
    <button
      type="button"
      aria-label="Show password"
      onclick="togglePasswordVisibility(this)"
    >
      👁
    </button>
  </div>
  <div id="password-requirements" class="password-strength">
    <div class="strength-bar" role="progressbar" aria-valuenow="60" aria-valuemin="0" aria-valuemax="100"></div>
    <ul class="requirements">
      <li data-met="true">At least 8 characters</li>
      <li data-met="true">Contains a number</li>
      <li data-met="false">Contains a special character</li>
    </ul>
  </div>
</div>
```

### Search Input

```html
<div class="search-input" role="search">
  <label for="search" class="sr-only">Search</label>
  <input
    type="search"
    id="search"
    placeholder="Search products..."
    aria-autocomplete="list"
    aria-controls="search-results"
  />
  <kbd class="search-shortcut" aria-hidden="true">⌘K</kbd>
</div>
```

### Date Input

```html
<!-- Native date picker (preferred for simple dates) -->
<input type="date" min="2024-01-01" max="2026-12-31" />

<!-- For date ranges, use two inputs -->
<fieldset>
  <legend>Travel dates</legend>
  <div class="date-range">
    <div>
      <label for="departure">Departure</label>
      <input type="date" id="departure" name="departure" />
    </div>
    <div>
      <label for="return">Return</label>
      <input type="date" id="return" name="return" />
    </div>
  </div>
</fieldset>
```

## Accessibility in Forms

### Form Grouping

```html
<!-- Group related fields with fieldset -->
<fieldset>
  <legend>Shipping Address</legend>
  <!-- address fields -->
</fieldset>

<!-- Group radio buttons -->
<fieldset>
  <legend>Preferred contact method</legend>
  <label><input type="radio" name="contact" value="email" /> Email</label>
  <label><input type="radio" name="contact" value="phone" /> Phone</label>
  <label><input type="radio" name="contact" value="sms" /> Text message</label>
</fieldset>
```

### Disabled vs. Read-Only

```html
<!-- Disabled: cannot interact, not submitted, grayed out -->
<input type="text" disabled value="Cannot change" />

<!-- Read-only: cannot edit, IS submitted, normal appearance -->
<input type="text" readonly value="Submitted but not editable" />
```

### Keyboard Navigation

- Tab moves between fields in document order
- Enter submits the form (ensure this works)
- Escape closes dropdowns/popovers without submitting
- Arrow keys navigate within radio groups and select elements

## Common Mistakes

### Disabling the Submit Button

- Problem: Button is disabled until form is valid — user doesn't know why
- Fix: Keep button enabled, show errors on submit

### Clearing Form on Error

- Problem: Server error resets all fields — user loses all input
- Fix: Preserve all entered values, highlight only the error field

### No Visible Labels

- Problem: Placeholder text used as the only label — disappears on input
- Fix: Always use visible `<label>` elements. Placeholders are hints, not labels.

### Ignoring Autofill

- Problem: Custom inputs break browser autofill
- Fix: Use standard `<input>` elements with correct `autocomplete` attributes

### Phone Number Formatting

- Problem: Strict format enforcement ("Must be (555) 555-5555")
- Fix: Accept any reasonable input, format on blur or server-side

### Generic Error Messages

- Problem: "An error occurred" — tells user nothing
- Fix: Specific, actionable messages: "Email address must include @ symbol"
