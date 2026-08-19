#!/bin/bash
# ============================================================
#  Clearspring — build the iOS app
#
#  Run on a Mac:   bash build-ios.sh
#
#  You need first:
#    - Xcode from the Mac App Store (large — start the download early)
#    - Node.js from https://nodejs.org
#    - CocoaPods:  sudo gem install cocoapods
# ============================================================

set -e
cd "$(dirname "$0")"

echo
if [ "$(uname)" != "Darwin" ]; then
  echo "  [X] iOS apps can only be built on a Mac."
  echo "      Apple requires Xcode, which is macOS only. Options:"
  echo "        - borrow a Mac"
  echo "        - a cloud Mac service (MacStadium, MacInCloud)"
  echo "        - GitHub Actions with a macOS runner"
  echo
  echo "      Android has no such restriction — use build-android.bat."
  echo
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "  [X] Node.js isn't installed. Get it from https://nodejs.org"
  echo
  exit 1
fi

if ! command -v pod >/dev/null 2>&1; then
  echo "  [!] CocoaPods isn't installed. Installing it now..."
  sudo gem install cocoapods
fi

echo "  Installing dependencies. First run takes a few minutes..."
echo
npm install

if [ ! -d "ios" ]; then
  echo
  echo "  Creating the iOS project..."
  npx cap add ios
fi

echo
echo "  Syncing..."
npx cap sync ios

echo
echo "  Opening Xcode."
echo
echo "  In Xcode:"
echo "    1. Click the project name in the left sidebar"
echo "    2. Signing & Capabilities -> pick your Apple Developer team"
echo "    3. Choose a device or simulator at the top"
echo "    4. Press the play button"
echo
npx cap open ios
