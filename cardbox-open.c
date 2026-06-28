#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdlib.h>
#include <stdio.h>

#define PIPE_NAME L"\\\\.\\pipe\\chappy.cardbox.ipc"
#define MAIN_EXE_NAME L"cardbox.exe"
#ifndef ASFW_ANY
#define ASFW_ANY ((DWORD)-1)
#endif

static void append_wchar(wchar_t **buf, size_t *cap, size_t *len, wchar_t ch) {
    if (*len + 2 >= *cap) {
        *cap = (*cap == 0) ? 1024 : (*cap * 2);
        *buf = (wchar_t *)realloc(*buf, sizeof(wchar_t) * (*cap));
    }
    (*buf)[(*len)++] = ch;
    (*buf)[*len] = 0;
}

static void append_wstr(wchar_t **buf, size_t *cap, size_t *len, const wchar_t *s) {
    while (s && *s) append_wchar(buf, cap, len, *s++);
}

static void append_quoted_arg(wchar_t **buf, size_t *cap, size_t *len, const wchar_t *arg) {
    append_wchar(buf, cap, len, L'"');
    int backslashes = 0;
    for (const wchar_t *p = arg; p && *p; ++p) {
        if (*p == L'\\') {
            backslashes++;
        } else if (*p == L'"') {
            for (int i = 0; i < backslashes * 2 + 1; ++i) append_wchar(buf, cap, len, L'\\');
            append_wchar(buf, cap, len, L'"');
            backslashes = 0;
        } else {
            for (int i = 0; i < backslashes; ++i) append_wchar(buf, cap, len, L'\\');
            backslashes = 0;
            append_wchar(buf, cap, len, *p);
        }
    }
    for (int i = 0; i < backslashes * 2; ++i) append_wchar(buf, cap, len, L'\\');
    append_wchar(buf, cap, len, L'"');
}

static char *wide_to_utf8(const wchar_t *w) {
    int len = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    if (len <= 0) return NULL;
    char *out = (char *)malloc((size_t)len);
    if (!out) return NULL;
    WideCharToMultiByte(CP_UTF8, 0, w, -1, out, len, NULL, NULL);
    return out;
}

static void append_bytes(char **buf, size_t *cap, size_t *len, const char *s) {
    while (s && *s) {
        if (*len + 2 >= *cap) {
            *cap = (*cap == 0) ? 1024 : (*cap * 2);
            *buf = (char *)realloc(*buf, *cap);
        }
        (*buf)[(*len)++] = *s++;
        (*buf)[*len] = 0;
    }
}

static void append_json_string(char **buf, size_t *cap, size_t *len, const wchar_t *w) {
    char *u = wide_to_utf8(w);
    append_bytes(buf, cap, len, "\"");
    if (u) {
        for (const unsigned char *p = (unsigned char *)u; *p; ++p) {
            char tmp[16];
            if (*p == '"' || *p == '\\') {
                tmp[0] = '\\'; tmp[1] = (char)*p; tmp[2] = 0;
                append_bytes(buf, cap, len, tmp);
            } else if (*p < 0x20) {
                sprintf(tmp, "\\u%04x", *p);
                append_bytes(buf, cap, len, tmp);
            } else {
                tmp[0] = (char)*p; tmp[1] = 0;
                append_bytes(buf, cap, len, tmp);
            }
        }
        free(u);
    }
    append_bytes(buf, cap, len, "\"");
}

static char *build_ipc_payload(int argc, wchar_t **argv) {
    char *buf = NULL;
    size_t cap = 0, len = 0;
    if (argc > 1) {
        append_bytes(&buf, &cap, &len, "{\"command\":\"open_images\",\"paths\":[");
        for (int i = 1; i < argc; ++i) {
            if (i > 1) append_bytes(&buf, &cap, &len, ",");
            append_json_string(&buf, &cap, &len, argv[i]);
        }
        append_bytes(&buf, &cap, &len, "]}\n");
    } else {
        append_bytes(&buf, &cap, &len, "{\"command\":\"show\"}\n");
    }
    return buf;
}

static BOOL try_send_ipc(int argc, wchar_t **argv) {
    AllowSetForegroundWindow(ASFW_ANY);
    if (!WaitNamedPipeW(PIPE_NAME, 80)) {
        // Try once anyway; the pipe may be available between checks.
    }
    HANDLE pipe = CreateFileW(PIPE_NAME, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (pipe == INVALID_HANDLE_VALUE) return FALSE;
    char *payload = build_ipc_payload(argc, argv);
    if (!payload) {
        CloseHandle(pipe);
        return FALSE;
    }
    DWORD written = 0;
    BOOL ok = WriteFile(pipe, payload, (DWORD)strlen(payload), &written, NULL);
    FlushFileBuffers(pipe);
    free(payload);
    CloseHandle(pipe);
    return ok;
}

static BOOL get_main_exe_path(wchar_t *out, DWORD count) {
    DWORD len = GetModuleFileNameW(NULL, out, count);
    if (len == 0 || len >= count) return FALSE;
    wchar_t *slash1 = wcsrchr(out, L'\\');
    wchar_t *slash2 = wcsrchr(out, L'/');
    wchar_t *slash = slash1 > slash2 ? slash1 : slash2;
    if (!slash) return FALSE;
    *(slash + 1) = 0;
    if (wcslen(out) + wcslen(MAIN_EXE_NAME) + 1 >= count) return FALSE;
    wcscat(out, MAIN_EXE_NAME);
    return TRUE;
}

static BOOL launch_main(int argc, wchar_t **argv) {
    wchar_t exe[MAX_PATH * 4];
    if (!get_main_exe_path(exe, (DWORD)(sizeof(exe) / sizeof(exe[0])))) return FALSE;

    wchar_t *cmd = NULL;
    size_t cap = 0, len = 0;
    append_quoted_arg(&cmd, &cap, &len, exe);
    for (int i = 1; i < argc; ++i) {
        append_wchar(&cmd, &cap, &len, L' ');
        append_quoted_arg(&cmd, &cap, &len, argv[i]);
    }

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);

    wchar_t workdir[MAX_PATH * 4];
    wcsncpy(workdir, exe, (sizeof(workdir) / sizeof(workdir[0])) - 1);
    workdir[(sizeof(workdir) / sizeof(workdir[0])) - 1] = 0;
    wchar_t *slash = wcsrchr(workdir, L'\\');
    if (slash) *slash = 0;

    BOOL ok = CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, workdir, &si, &pi);
    if (ok) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
    free(cmd);
    return ok;
}

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, PWSTR pCmdLine, int nCmdShow) {
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) return 1;

    if (try_send_ipc(argc, argv)) {
        LocalFree(argv);
        return 0;
    }

    BOOL ok = launch_main(argc, argv);
    LocalFree(argv);
    return ok ? 0 : 2;
}
