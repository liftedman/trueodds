@echo off
REM Re-push the prediction snapshot to Supabase (run on a schedule).
REM Logs to data\push.log. Uses the venv python directly (no PATH needed).
cd /d C:\NJS\sports-model
.\.venv\Scripts\python.exe -m sports_model.main push >> data\push.log 2>&1
