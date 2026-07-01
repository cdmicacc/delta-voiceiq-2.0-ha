# mitmproxy (Historical / Debugging Only)

This integration's setup flow no longer requires mitmproxy — the config flow's sign-in-and-paste-code steps (see the README's Quick Start) work for both first-time setup and token refresh, using the same `Auth/Login` → `PostAuth` → `UserInfo` flow this project originally reverse-engineered using mitmproxy.

mitmproxy is still useful if you're debugging the Delta API itself (e.g. confirming a header or endpoint behaves as documented in [API.md](API.md)), but it is not part of normal setup or use.
