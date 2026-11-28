# Maestro run procedure (stage 2)

Manual for now. A nightly schedule needs the user's explicit approval (spec: "נקודות אישור").

1. Find the newest folder `earnings-insight/dossiers/<date>/` and read `index.json`.
2. For each dossier (rank order): skip if `Modi-in/verdicts/<date>/<TICKER>.json` exists and the dossier is unchanged.
3. Run `python3 agents/extract.py <dossier folder>` and read only that compact view (raw dossiers are ~1 MB for 20). Auditor: apply `agents/auditor.md` → finding JSON.
4. Maestro: read `agents/maestro.md`, apply it to the finding + the listed dossier fields → verdict JSON.
5. Validate the verdict against `verdict.schema.json` (python3 -m json.tool + required keys); write
   `verdicts/<date>/<TICKER>.json`, then `verdicts/<date>/SUMMARY.md` (Hebrew table: ticker, score, confidence, conflict).
6. Record in `verdicts/<date>/RUN_LOG.md`: number of dossiers, total characters read (dossier sizes), wall time — the
   quota measurement the spec asks for in stage 2.
7. Commit to Modi-in. Do not write to the database (stage 4, needs approval). No Claude API, no Lovable credits.
