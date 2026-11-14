# DEVELOPMENT_ROADMAP

| שלב | תוכן | בדיקות קבלה |
|---|---|---|
| **M0 תשתית** | פרויקט Lovable + Cloud; טבלאות ליבה (companies, scan_jobs, scan_results, financial_statements, source_documents, data_quality_logs); Auth משתמש יחיד; Secrets | טבלאות + הרשאות; אין סוד בקוד הדפדפן |
| **M1 נתונים אמיתיים** | Edge Function `refresh-company` (SEC → XBRL → מדדים → ציון בריאות, עם מקור ותאריך); מסכי Financial Health + System Status + כפתור Refresh Data | 3 חברות אמיתיות (MSFT, CRWD, NVDA) — הכנסות/רווח/מזומן/חוב תואמים 10-Q/10-K; פלט TS = פלט Python על נתוני הבדיקה; חוסרים מסומנים |
| M2 Scan Market | לוח Finnhub + מחיר; תור עבודות ב-Jobs; התקדמות וספירות | Job עם ספירות אמיתיות; כשל ספק מוצג |
| M3 | שווי, Fallen Angels, ציון דילול, בעלי עניין, דגלים, Override | |
| M4 | Earnings Intelligence, צילומי קונצנזוס, דוח 9 פרקים, ייצוא | |
| M5 | היסטוריית מחירים, חלונות החזקה, Backtesting | יום 0 נכון ל-AMC/BMO |
| M6 | רשימת מעקב, התראות, Jobs מתוזמנים, Dashboard | Job רץ ללא דפדפן |
