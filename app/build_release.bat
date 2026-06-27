@echo off
REM ============================================================
REM  TrueOdds — one-shot release build
REM  Run from the app\ folder:   build_release.bat
REM ============================================================
setlocal

echo.
echo [1/5] Fetching packages...
call flutter pub get || goto :err

echo.
echo [2/5] Generating launcher icons...
call dart run flutter_launcher_icons || goto :err

echo.
echo [3/5] Generating native splash screen...
call dart run flutter_native_splash:create || goto :err

echo.
echo [4/5] Building release APK (installable / shareable)...
call flutter build apk --release || goto :err

echo.
echo [5/5] Building release web bundle...
call flutter build web --release || goto :err

echo.
echo ============================================================
echo  DONE.
echo   APK : build\app\outputs\flutter-apk\app-release.apk
echo   Web : build\web\   (deploy this folder to any static host)
echo ============================================================
goto :eof

:err
echo.
echo *** Build step failed. Fix the error above and re-run. ***
exit /b 1
