# engine-ts — מנוע החישובים ב-TypeScript

הסבה של `python/evi` ל-TypeScript, להרצה ב-Edge Functions של Lovable Cloud (Deno) ובדפדפן. ללא תלויות חיצוניות.

| קובץ | מקור Python | סטטוס |
|---|---|---|
| `engine/xbrl.ts` | `providers/xbrl.py` | ✅ זהה לפלט Python |
| `engine/metrics.ts` | `analytics/metrics.py` | ✅ זהה |
| `engine/health.ts` | `analytics/scores.py` (health) | ✅ זהה |

**בדיקת השוואה:** `node engine-ts/tests/parity.test.ts` (Node 22+) — 294/294. קובץ המקרים `parity_cases.json` נוצר מקוד ה-Python על נתוני הבדיקה.
יעד סופי: `supabase/functions/_shared/engine/` במאגר של Lovable.
