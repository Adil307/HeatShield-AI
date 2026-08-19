# Day 10.1.1 — Dashboard Asset Cache Fix

## Problem

The browser loaded the redesigned Day 10.1 HTML while reusing the older Day 10 stylesheet from cache.
That produced a broken hybrid layout: new markup rendered with old CSS.

Changing the page URL query (for example `/dashboard/?v=10.1`) does not automatically version
the linked `styles.css` and `app.js` resources.

## Fix

The dashboard now uses versioned asset URLs:

```html
<link rel="stylesheet" href="./styles.css?v=10.1.1" />
<script src="./app.js?v=10.1.1"></script>
```

This forces the browser to request the matching Day 10.1 assets and prevents the stale-CSS/new-HTML mismatch.

No backend decision logic, FortyGuard evidence, local Qwen integration, or evidence guard behavior is changed.
