# Browser

Prefer locators in this order: role, label, test id, CSS, XPath, coordinate.
Keep sessions in the adapter, record navigation and downloads as Evidence, and
put every browser mutation inside an Action Boundary with post-action
Verification. Treat unstable pages as explicit retry or reconciliation state.
