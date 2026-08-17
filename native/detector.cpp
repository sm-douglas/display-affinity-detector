// detector.cpp
// Enumera todas as janelas top-level visiveis e reporta o valor
// de display affinity de cada uma, usando GetWindowDisplayAffinity.
//
// Valores possiveis de DWORD affinity:
//   WDA_NONE               0x00000000  -> sem restricao
//   WDA_MONITOR            0x00000001  -> (legado) exclui de captura
//   WDA_EXCLUDEFROMCAPTURE 0x00000011  -> exclui de captura (Win10 2004+)
//
// Compilar (MSVC):
//   cl /EHsc detector.cpp user32.lib
//
// Compilar (MinGW):
//   g++ detector.cpp -o detector.exe -luser32

#ifdef _WIN32_WINNT
#undef _WIN32_WINNT
#endif
#define _WIN32_WINNT 0x0A00  // Windows 10, necessario para GetWindowDisplayAffinity

#ifdef WINVER
#undef WINVER
#endif
#define WINVER 0x0A00

#include <windows.h>
#include <iostream>
#include <vector>
#include <string>

// Declaracao manual: alguns headers de MinGW mais antigos/legados nao
// incluem essa funcao mesmo com _WIN32_WINNT/WINVER definidos corretamente.
// A funcao existe de verdade em user32.dll desde o Windows 7, entao
// declarar aqui e linkar contra user32.lib funciona independente do header.
#ifndef GWDA_DECLARED_MANUALLY
#define GWDA_DECLARED_MANUALLY
extern "C" __declspec(dllimport) BOOL WINAPI GetWindowDisplayAffinity(HWND hWnd, DWORD* pdwAffinity);
#endif

struct WindowInfo {
    HWND hwnd;
    std::wstring title;
    DWORD affinity;
    bool queryOk;
};

std::vector<WindowInfo> g_results;

BOOL CALLBACK EnumWindowsCallback(HWND hwnd, LPARAM lParam) {
    if (!IsWindowVisible(hwnd)) return TRUE;

    wchar_t title[256];
    int len = GetWindowTextW(hwnd, title, 256);
    if (len == 0) return TRUE; // ignora janelas sem titulo (geralmente utilitarias)

    DWORD affinity = 0;
    BOOL ok = GetWindowDisplayAffinity(hwnd, &affinity);

    WindowInfo info;
    info.hwnd = hwnd;
    info.title = std::wstring(title, len);
    info.affinity = affinity;
    info.queryOk = ok;

    g_results.push_back(info);
    return TRUE;
}

const wchar_t* AffinityToString(DWORD affinity) {
    switch (affinity) {
        case 0x00000000: return L"WDA_NONE (sem protecao)";
        case 0x00000001: return L"WDA_MONITOR (legado, exclui de captura)";
        case 0x00000011: return L"WDA_EXCLUDEFROMCAPTURE (exclui de captura)";
        default: return L"DESCONHECIDO";
    }
}

int main() {
    EnumWindows(EnumWindowsCallback, 0);

    std::wcout << L"Janelas visiveis analisadas: " << g_results.size() << L"\n\n";

    for (const auto& info : g_results) {
        std::wcout << L"HWND: " << info.hwnd
                    << L" | Titulo: " << info.title << L"\n";

        if (!info.queryOk) {
            std::wcout << L"  -> Falha ao consultar affinity (GetLastError: "
                        << GetLastError() << L")\n";
            continue;
        }

        std::wcout << L"  -> Affinity: 0x" << std::hex << info.affinity
                    << std::dec << L" (" << AffinityToString(info.affinity) << L")\n";

        if (info.affinity != 0) {
            std::wcout << L"  ** Esta janela esta protegida contra captura de tela **\n";
        }
        std::wcout << L"\n";
    }

    return 0;
}
