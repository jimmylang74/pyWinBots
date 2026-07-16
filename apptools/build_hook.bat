@echo off
REM build_hook.bat — Compile mouse_hook.dll using MinGW (x86_64)
REM
REM Prerequisites:
REM   - MinGW-w64 installed and on PATH (e.g. MSYS2 mingw64 toolchain)
REM   OR
REM   - Visual Studio Build Tools with cl.exe on PATH
REM
REM Usage:
REM   cd apptools
REM   build_hook.bat

where gcc >nul 2>&1
if %errorlevel%==0 (
    echo [build] Using MinGW GCC
    gcc -shared -o mouse_hook.dll mouse_hook.c -luser32 -lole32 -Wl,--out-implib,libmouse_hook.a -O2 -s
    goto :check
)

where cl >nul 2>&1
if %errorlevel%==0 (
    echo [build] Using MSVC cl.exe
    cl /LD mouse_hook.c /link /OUT:mouse_hook.dll user32.lib ole32.lib /OPT:REF
    goto :check
)

echo [build] ERROR: No compiler found. Install MinGW-w64 or Visual Studio Build Tools.
exit /b 1

:check
if exist mouse_hook.dll (
    echo [build] OK — mouse_hook.dll built successfully
) else (
    echo [build] FAILED — mouse_hook.dll was not produced
    exit /b 1
)
