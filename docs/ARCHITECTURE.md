# ARCHITECTURE

```
SEC EDGAR ─┐                                   ┌─> Lovable UI (React, RTL)
Finnhub  ──┼─> Edge Functions (TypeScript/Deno) ┤
(Massive)──┘    ingest → validate → engine      └─> Lovable Cloud DB (sole app DB)
                    ▲                                    ▲
                Jobs (scheduled scans)          Secrets (API keys, server-side only)
```

- **Lovable Cloud**: מסד נתונים, Auth (משתמש יחיד), Storage, Secrets, Edge Functions, Jobs.
- **מנוע**: הסבה של `python/evi/analytics` + `providers/xbrl.py` ל-TypeScript. כל פונקציה מקבלת אותם נתוני בדיקה כמו ב-Python וחייבת להחזיר אותן תוצאות (בדיקת השוואה).
- **סריקה**: תור עבודות — `scan_jobs` + `scan_results`; Job מעבד אצוות קטנות (זמן ריצה מקסימלי של Edge Function לא מתועד — יש לאמת).
- **ללא** Python מארח, **ללא** מסד נתונים נוסף.
- **GitHub**: Lovable יוצר מאגר חדש משלו לסנכרון (לא ניתן לחבר מאגר קיים — לפי תיעוד Lovable). ראה החלטה פתוחה ב-PROJECT_STATE.
