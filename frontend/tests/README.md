# Main-chat regression checks

No packages or application server are required. Run from the repository root:

```sh
node --test frontend/tests/*.test.cjs
node --check frontend/js/chat.js
```

- `chat.test.cjs` uses Node's built-in test runner and VM to execute the real
  `ChatManager`. It replaces only leaf DOM operations and supplies deferred
  conversation requests/stream events. It covers out-of-order selection,
  creation/deletion during loading, neutral pre-metadata typing labels,
  stream isolation across navigation, errors, title ownership, and returning
  to the original chat before a response completes.
- `chat-layout.test.cjs` requires Node 22+ (built-in `WebSocket`) and an installed
  Firefox (`FIREFOX_BIN` can override the binary). It skips if Firefox is absent.
  Reduced motion is enabled so entrance animations cannot skew measurements.
  The test uses Firefox's built-in WebDriver BiDi endpoint directly: no Selenium,
  Playwright, or driver installation. It checks the real HTML/CSS at widths
  320, 375, 390, 760, and 1280, with and without a long active-agent name.
  A long model name must not push the export button outside the viewport, the
  send/agent-clear buttons remain usable, and wide code scrolls within its bubble.

The browser fixture is built in a temporary directory from `index.html` and
`globals.css`. All scripts, asset links, and the remote font import are removed.
Firefox runs in a disposable profile with external HTTP(S) proxied to a closed
loopback port. The test cleans up that process and profile. These checks do not
read app data, run the backend, or call model/email/calendar services.

## Intentional limits

- Sending remains single-flight across conversations, as before. Navigation is
  still available while a response is running. Offscreen streams continue to
  completion without writing into the visible chat.
- Returning to the originating conversation mid-stream shows its saved history
  and a neutral typing indicator, then reloads the saved response when the
  stream ends. It does not replay offscreen token animations.
- Browser coverage is desktop Firefox at narrow viewport sizes, not a physical
  mobile device, mobile keyboard, Safari, or Chromium. Remote fonts and markdown
  libraries are excluded from the isolated layout fixture.
