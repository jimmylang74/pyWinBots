#!/bin/bash
# build_hook.sh — Compile mouse_hook.dll using MinGW-w64 cross-compiler
#
# Prerequisites:
#   sudo apt install mingw-w64
#
# Usage:
#   cd apptools
#   ./build_hook.sh

set -e

CC=x86_64-w64-mingw32-gcc
OUT=mouse_hook.dll
SRC=mouse_hook.c

if ! command -v $CC &> /dev/null; then
    echo "[build] ERROR: $CC not found. Install: sudo apt install mingw-w64"
    exit 1
fi

echo "[build] Compiling $OUT with $CC"
$CC -shared -o $OUT $SRC -luser32 -lole32 -O2 -s

if [ -f "$OUT" ]; then
    echo "[build] OK — $OUT built successfully ($(du -h $OUT | cut -f1))"
else
    echo "[build] FAILED — $OUT was not produced"
    exit 1
fi
