/**
 * mouse_hook.c — WH_MOUSE_LL hook DLL with zero Python overhead.
 *
 * The low-level mouse hook callback runs entirely in C. Python never
 * enters the call stack during hook processing, so there is no GIL
 * contention and no per-event Python interpreter overhead.
 *
 * DLL exports:
 *   InstallHook()             — SetWindowsHookExW(WH_MOUSE_LL, …), returns HHOOK
 *   UninstallHook()           — UnhookWindowsHookEx + PostThreadMessage(WM_QUIT)
 *   RunMessagePump()          — GetMessage loop (blocks until WM_QUIT)
 *   StopMessagePump()         — Posts WM_QUIT to the pump thread
 *   GetMousePos(x*, y*)       — Writes current mouse position into caller's ints
 *   HasNewEvent()             — Returns 1 if position changed since last call, 0 otherwise
 *   HasWindowInfo()           — Returns 1 if new idle window info available, 0 otherwise
 *   GetIdleWindowHandle()     — Returns HWND of the window under cursor at idle
 *   GetIdleWindowRect(l,t,r,b*) — Writes window RECT at idle
 *   GetIdleWindowName(buf, len) — Copies window title to buffer (WCHAR)
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

/* ------------------------------------------------------------------ */
/* Shared state                                                        */
/* ------------------------------------------------------------------ */

static HHOOK  g_hook       = NULL;
static HHOOK  g_hhook_ret  = NULL;
static DWORD  g_pump_tid   = 0;
static int    g_mouse_x    = 0;
static int    g_mouse_y    = 0;
static int    g_new_event  = 0;
static int    g_pump_stop  = 0;

/* Idle detection state */
static DWORD  g_last_move_tick   = 0;
static int    g_idle_fired       = 0;     /* 1 = already fired for current idle period */
static HWND   g_idle_hwnd        = NULL;
static RECT   g_idle_rect        = {0};
static WCHAR  g_idle_name[256]   = {0};
static int    g_has_window_info  = 0;     /* 1 = new info available for Python to read */

#define IDLE_TIMEOUT_MS   1000
#define CHECK_INTERVAL_MS 200
#define IDT_CHECK_IDLE    1

/* ------------------------------------------------------------------ */
/* Hook callback — runs in the pump thread's message queue context      */
/* ------------------------------------------------------------------ */

static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode >= 0) {
        LONG x = ((LONG*)lParam)[0];
        LONG y = ((LONG*)lParam)[1];
        g_mouse_x    = x;
        g_mouse_y    = y;
        g_new_event  = 1;
        g_last_move_tick = GetTickCount();
        g_idle_fired = 0;
    }
    return CallNextHookEx(g_hhook_ret, nCode, wParam, lParam);
}

/* ------------------------------------------------------------------ */
/* Timer: check idle and retrieve window info                          */
/* ------------------------------------------------------------------ */

static void CheckIdle(void) {
    DWORD now = GetTickCount();
    if (g_idle_fired)
        return;
    if (g_last_move_tick == 0 || (now - g_last_move_tick) < IDLE_TIMEOUT_MS)
        return;

    POINT pt;
    pt.x = g_mouse_x;
    pt.y = g_mouse_y;

    HWND hwnd = WindowFromPoint(pt);
    if (!hwnd)
        return;
    hwnd = GetAncestor(hwnd, GA_ROOT);
    if (!hwnd)
        return;

    GetWindowRect(hwnd, &g_idle_rect);

    int len = GetWindowTextW(hwnd, g_idle_name, 256);
    if (len == 0)
        g_idle_name[0] = L'\0';

    g_idle_hwnd       = hwnd;
    g_has_window_info = 1;
    g_idle_fired      = 1;
}

/* ------------------------------------------------------------------ */
/* Exports                                                             */
/* ------------------------------------------------------------------ */

__declspec(dllexport) HHOOK InstallHook(void) {
    g_hhook_ret      = SetWindowsHookExW(WH_MOUSE_LL, MouseProc, NULL, 0);
    g_hook           = g_hhook_ret;
    g_pump_stop      = 0;
    g_last_move_tick = 0;
    g_idle_fired     = 0;
    return g_hhook_ret;
}

__declspec(dllexport) void UninstallHook(void) {
    if (g_hook) {
        UnhookWindowsHookEx(g_hook);
        g_hook      = NULL;
        g_hhook_ret = NULL;
    }
}

__declspec(dllexport) void RunMessagePump(void) {
    g_pump_tid = GetCurrentThreadId();
    g_pump_stop = 0;

    SetTimer(NULL, IDT_CHECK_IDLE, CHECK_INTERVAL_MS, NULL);

    MSG msg;
    while (!g_pump_stop && GetMessage(&msg, NULL, 0, 0)) {
        if (msg.message == WM_TIMER && msg.wParam == IDT_CHECK_IDLE) {
            CheckIdle();
            continue;
        }
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    KillTimer(NULL, IDT_CHECK_IDLE);
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

__declspec(dllexport) int HasWindowInfo(void) {
    int v = g_has_window_info;
    g_has_window_info = 0;
    return v;
}

__declspec(dllexport) void* GetIdleWindowHandle(void) {
    return (void*)(intptr_t)g_idle_hwnd;
}

__declspec(dllexport) void GetIdleWindowRect(int *left, int *top, int *right, int *bottom) {
    if (left)  *left  = g_idle_rect.left;
    if (top)   *top   = g_idle_rect.top;
    if (right) *right = g_idle_rect.right;
    if (bottom)*bottom= g_idle_rect.bottom;
}

__declspec(dllexport) int GetIdleWindowName(wchar_t *buf, int bufLen) {
    if (!buf || bufLen <= 0)
        return 0;
    int len = (int)wcslen(g_idle_name);
    int copy = (len < bufLen - 1) ? len : bufLen - 1;
    memcpy(buf, g_idle_name, copy * sizeof(wchar_t));
    buf[copy] = L'\0';
    return copy;
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    (void)hinst; (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}
