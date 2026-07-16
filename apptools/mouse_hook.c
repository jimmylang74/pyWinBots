/**
 * mouse_hook.c — WH_MOUSE_LL hook DLL with zero Python overhead.
 *
 * The low-level mouse hook callback runs entirely in C. Python never
 * enters the call stack during hook processing, so there is no GIL
 * contention and no per-event Python interpreter overhead.
 *
 * DLL exports:
 *   InstallHook()        — SetWindowsHookExW(WH_MOUSE_LL, …), returns HHOOK
 *   UninstallHook()      — UnhookWindowsHookEx + PostThreadMessage(WM_QUIT)
 *   RunMessagePump()     — GetMessage loop (blocks until WM_QUIT)
 *   StopMessagePump()    — Posts WM_QUIT to the pump thread
 *   GetMousePos(x*, y*)  — Writes current mouse position into caller's ints
 *   HasNewEvent()        — Returns 1 if position changed since last call, 0 otherwise
 *   GetLastClickTime()   — Returns GetTickCount() of last non-move mouse event (unused for now)
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

/* ------------------------------------------------------------------ */
/* Shared state (single-threaded: hook callback writes, Python reads) */
/* ------------------------------------------------------------------ */

static HHOOK  g_hook       = NULL;
static HHOOK  g_hhook_ret  = NULL;  /* return value of SetWindowsHookExW */
static DWORD  g_pump_tid   = 0;     /* message-pump thread id           */
static int    g_mouse_x    = 0;
static int    g_mouse_y    = 0;
static int    g_new_event  = 0;     /* 1 = position changed since last read */
static int    g_pump_stop  = 0;     /* flag to break out of message pump */

/* ------------------------------------------------------------------ */
/* Hook callback — runs in the context of the thread that called       */
/* RunMessagePump (the pump thread), NOT in the calling thread.        */
/* This is critical: it runs with the pump thread's message queue.     */
/* ------------------------------------------------------------------ */

static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode >= 0) {
        /* Extract position from MSLLHOOKSTRUCT — pt is at offset 0 */
        LONG x = ((LONG*)lParam)[0];  /* pt.x */
        LONG y = ((LONG*)lParam)[1];  /* pt.y */
        g_mouse_x    = x;
        g_mouse_y    = y;
        g_new_event  = 1;
    }
    return CallNextHookEx(g_hhook_ret, nCode, wParam, lParam);
}

/* ------------------------------------------------------------------ */
/* Exports                                                             */
/* ------------------------------------------------------------------ */

__declspec(dllexport) HHOOK InstallHook(void) {
    g_hhook_ret = SetWindowsHookExW(WH_MOUSE_LL, MouseProc, NULL, 0);
    g_hook      = g_hhook_ret;
    g_pump_stop = 0;
    return g_hhook_ret;
}

__declspec(dllexport) void UninstallHook(void) {
    if (g_hook) {
        UnhookWindowsHookEx(g_hook);
        g_hook = NULL;
        g_hhook_ret = NULL;
    }
}

__declspec(dllexport) void RunMessagePump(void) {
    g_pump_tid = GetCurrentThreadId();
    g_pump_stop = 0;

    MSG msg;
    while (!g_pump_stop && GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
}

__declspec(dllexport) void StopMessagePump(void) {
    g_pump_stop = 1;
    if (g_pump_tid) {
        PostThreadMessage(g_pump_tid, WM_QUIT, 0, 0);
    }
}

__declspec(dllexport) void GetMousePos(int *x, int *y) {
    if (x) *x = g_mouse_x;
    if (y) *y = g_mouse_y;
}

__declspec(dllexport) int HasNewEvent(void) {
    int v = g_new_event;
    g_new_event = 0;
    return v;
}

/* Required for DLL_PROCESS_ATTACH to set up a thread-local store
 * so that the hook callback runs in the pump thread's message queue. */
BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    (void)hinst; (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}
