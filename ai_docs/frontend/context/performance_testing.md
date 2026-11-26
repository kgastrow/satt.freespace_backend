# Frontend Performance Testing

Lighthouse CI for Core Web Vitals and bundle size tracking.

## Running

```bash
# From app/frontend/
npm run perf          # Run Lighthouse CI (starts dev server automatically)
npm run perf:report   # Open results in browser
```

## Configuration

**`app/frontend/lighthouserc.json`** - Lighthouse CI config:
- Audits `http://localhost:5173/` and `/login`
- 3 runs per URL, desktop preset
- Results saved to `./lighthouse-results/`

## Thresholds (CI Gate)

| Metric | Target | Severity |
|--------|--------|----------|
| Performance Score | >= 90 | Error |
| LCP (Largest Contentful Paint) | < 2.5s | Error |
| TTI (Time to Interactive) | < 3.5s | Error |
| CLS (Cumulative Layout Shift) | < 0.1 | Error |
| Total Bundle Size | < 512KB | Warning |

## Adding Pages to Audit

Edit the `url` array in `lighthouserc.json`:
```json
"url": [
  "http://localhost:5173/",
  "http://localhost:5173/login",
  "http://localhost:5173/your-new-page"
]
```

## CI

The `frontend-lighthouse` job in `.github/workflows/perf.yml` runs on PRs to main and weekly (Monday 2am). Results uploaded as artifacts.
