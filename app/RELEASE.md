# TrueOdds — Release Guide

Everything needed to turn the app into something you can install on a phone or
deploy to the web. Run all commands from the `app\` folder.

## Quick build (recommended)

```bat
build_release.bat
```

This runs the whole pipeline: `pub get` → launcher icons → native splash →
release APK → web bundle. Outputs:

- **APK** (sideload / share): `build\app\outputs\flutter-apk\app-release.apk`
- **Web** (deploy anywhere static): `build\web\`

The APK is signed with the debug key, which is fine for sharing and installing
directly. For the Play Store you need your own key — see below.

## Manual steps (if you prefer)

```bat
flutter pub get
dart run flutter_launcher_icons          REM app icon on every platform
dart run flutter_native_splash:create    REM OS launch screen
flutter build apk --release              REM single installable APK
flutter build web --release              REM static web build
```

To regenerate the icon artwork itself (teal mark): `python tool\make_icons.py`,
then re-run the two `dart run` commands above.

## Installing the APK on a phone

1. Copy `app-release.apk` to the phone (USB, Drive, email to yourself).
2. Tap it; allow "install from unknown sources" when prompted.
3. The TrueOdds icon appears in the launcher.

## Deploying the web build

`build\web\` is a static site. Drop it on any static host:

- **Netlify / Vercel / Cloudflare Pages**: point the project at `build\web`.
- **Firebase Hosting**: `firebase init hosting` (public dir = `build/web`), then `firebase deploy`.
- **GitHub Pages**: push the contents of `build\web` to a `gh-pages` branch.

## Play Store signing (only when you publish there)

1. Create a keystore (one time):
   ```bat
   keytool -genkey -v -keystore %USERPROFILE%\trueodds-upload.jks ^
     -keyalg RSA -keysize 2048 -validity 10000 -alias upload
   ```
2. Create `android\key.properties` (do NOT commit it):
   ```
   storePassword=YOUR_STORE_PASSWORD
   keyPassword=YOUR_KEY_PASSWORD
   keyAlias=upload
   storeFile=C:/Users/YOU/trueodds-upload.jks
   ```
3. Wire it into `android\app\build.gradle.kts` (replace the `release` block's
   `signingConfig = signingConfigs.getByName("debug")` with a real config that
   reads `key.properties`). Then:
   ```bat
   flutter build appbundle --release
   ```
   Upload `build\app\outputs\bundle\release\app-release.aab` to the Play Console.

## Identity

- App name: **TrueOdds** (`android:label` in AndroidManifest.xml)
- Application ID: `com.trueodds.app`
- Brand colour: `#0EA5A4`
