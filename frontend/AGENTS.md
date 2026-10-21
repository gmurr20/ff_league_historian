# frontend/AGENTS.md — Frontend Architecture & Mobile PWA Guidelines

> **Scope:** This guide governs the Vue 3 mobile application (`frontend/`), TypeScript type definitions (`src/types/`), API client (`src/api/client.ts`), Tailwind CSS design tokens, and Workbox PWA caching policies.

---

## 1. Architectural Stack

- **Framework:** Vue 3 Composition API with `<script setup lang="ts">`.
- **Bundler:** Vite + `vite-plugin-pwa`.
- **Styling:** Tailwind CSS with custom stadium/athletic dark theme tokens.
- **State Management:** Lightweight Vue composables (`useLeagueMeta`, `useSeasonSelector`) or Pinia.
- **TypeScript:** Strict type checking (`strict: true`, `noImplicitAny: true`).

---

## 2. Strict Type Contract Mirroring

- **Source of Truth:** All API types in `frontend/src/types/api.ts` MUST directly mirror [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md).
- **Rule:** Never define ad-hoc `any` types for API payloads. If an endpoint response changes, update `docs/api-contracts.md` and `frontend/src/types/api.ts` in lockstep.
- **Null Safety:** Pay attention to nullable fields (e.g. `co_manager_name: string | null`, `winner_manager_id: number | null`, `faab_remaining: number | null`). Handle `null` values gracefully with fallback UI displays.

---

## 3. Mobile-First Stadium Athletic UI Design

### 3.1 Design Tokens & Aesthetic
- **Color Palette:**
  - Background: Deep stadium charcoal/black (`#0a0d14` / `#111622`).
  - Cards/Surfaces: Elevated slate dark (`#182030` / `#1e293b`).
  - Accents: Turf emerald (`#10b981`), Trophy gold (`#f59e0b`), Alert coral (`#f43f5e`).
  - Text: Primary `#f8fafc`, Secondary `#94a3b8`, Muted `#64748b`.
- **Typography:** Athletic sans-serif font family with clean tabular numbers (`font-mono` / `tabular-nums`) for scores, records, and financial amounts.

### 3.2 Mobile Touch & iOS Safe Areas
- **Touch Targets:** Minimum 44×44px interactive areas.
- **Safe Area Insets:** Ensure navigation bars, sticky headers, and bottom tab bars respect iOS notch and home indicator:
  ```css
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
  ```
- **Navigation:** Bottom navigation bar with 5 primary tabs:
  1. **Standings** (Current & historical records, All-Play, Luck index)
  2. **Earnings** (Financial bankroll, weekly vs. podium breakdown)
  3. **Head-to-Head** (Career rivalry matrix & Tale of the Tape)
  4. **Trades** (Trade network, realized post-trade starter points)
  5. **Waivers** (FAAB ROI, waiver efficiency, failed bids & bidding wars)

---

## 4. Workbox PWA & Service Worker Caching Rules

In `vite.config.ts` (Vite PWA plugin):
1. **API Requests (`/api/v1/*`):**
   - **Strategy:** `NetworkFirst`.
   - **Options:** Cache name `'api-cache'`, short network timeout (3 seconds), cache expiration (max entries: 50, max age: 1 day).
   - **Reason:** Online users must immediately receive the latest standings and payouts; offline users retain full read capability from cache.
2. **Static Bundles (`.js`, `.css`, `.png`, `.svg`):**
   - **Strategy:** `CacheFirst`.
   - **Reason:** Content-hashed assets can be permanently cached.
3. **Player Headshots & External Images:**
   - **Strategy:** `StaleWhileRevalidate` with LRU eviction.

---

## 5. Verification & Linting

Before submitting code, ensure:
- `vue-tsc --noEmit` passes with 0 type errors.
- `vite build` generates the production bundle into `frontend/dist/`.
- No horizontal overflow on 375px mobile viewports (iPhone SE / standard mobile breakpoint).
