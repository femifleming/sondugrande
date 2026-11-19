#!/bin/sh
# Prints manual.html to "Sondugrande Manual.pdf" with headless Chrome (as the
# author's other manuals are made). Run make_shots.py first for the pictures.
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="Sondugrande Manual.pdf" "file://$PWD/manual.html" 2>/dev/null
ls -la "Sondugrande Manual.pdf"
