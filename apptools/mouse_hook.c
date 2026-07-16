/**
 * mouse_hook.c — WH_MOUSE_LL hook DLL with Python callback delegation.
 *
 * The DLL installs a global low-level mouse hook and delegates each
 * event to a Python callback via WINFUNCTYPE. The callback runs in
 * the pump thread's message queue context.
 *
 * DLL exports:
 *   InstallHook(callback) — SetWindowsHookExW, returns HHOOK
 *   UninstallHook()       — UnhookWindowsHookEx
 *   RunMessagePump()      — GetMessage loop (blocks until WM_QUIT)
 *   StopMessagePump()     — Posts WM_QUIT to the pump thread
 *   CallNext(hookId, nCode, wParam, lParam) — CallNextHookEx wrapper
 */

#define WIN32_LEAN_MEAN
#include <windows.h>

static HINSTANCE g_hinst    = NULL;
static HHOOK    g_hook      = NULL;
static HHOOK    g_hhook_ret = NULL;
static DWORD    g_pump_tid  = 0;
static int      g_pump_stop = 0;

typedef LRESULT (*HOOK_CB)(int, WPARAM, LPARAM);
static HOOK_CB g_python_cb = NULL;

static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode >= 0 && g_python_cb) {
        return g_python_cb(nCode, wParam, lParam);
    }
    return CallNextHookEx(g_hhook_ret, nCode, wParam, lParam);
}

__declspec(dllexport) HHOOK InstallHook(void *callback) {
    g_python_cb = (HOOK_CB)callback;

    MSG msg;
    PeekMessage(&msg, NULL, 0, 0, PM_NOREMOVE);

    g_hhook_ret = SetWindowsHookExW(WH_MOUSE_LL, MouseProc, g_hinst, 0);
    g_hook      = g_hhook_ret;
    g_pump_stop = 0;
    return g_hhook_ret;
}

__declspec(dllexport) void UninstallHook(void) {
    if (g_hook) {
        UnhookWindowsHookEx(g_hook);
        g_hook      = NULL;
        g_hhook_ret = NULL;
    }
    g_python_cb = NULL;
}

__declspec(dllexport) void RunMessagePump(void) {
    g_pump_tid  = GetCurrentThreadId();
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

__declspec(dllexport) LRESULT CallNext(LRESULT hookId, int nCode, WPARAM wParam, LPARAM lParam) {
    return CallNextHookEx((HHOOK)hookId, nCode, wParam, lParam);
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_hinst = hinst;
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}
