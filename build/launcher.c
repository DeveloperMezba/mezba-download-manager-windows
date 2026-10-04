#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdlib.h>

static void append_quoted(wchar_t *out, const wchar_t *arg) {
    wcscat(out,L"\"");
    unsigned slash=0;
    for (;*arg;arg++) {
        if (*arg==L'\\') {slash++;continue;}
        if (*arg==L'\"') {
            for (unsigned i=0;i<2*slash+1;i++) wcscat(out,L"\\");
        } else for (unsigned i=0;i<slash;i++) wcscat(out,L"\\");
        slash=0;size_t n=wcslen(out);out[n]=*arg;out[n+1]=0;
    }
    for (unsigned i=0;i<2*slash;i++) wcscat(out,L"\\");
    wcscat(out,L"\" ");
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,LPWSTR command,int show) {
    wchar_t self[32768],root[32768],python[32768],script[32768];
    if(!GetModuleFileNameW(NULL,self,32768))return 1;
    wcscpy(root,self);wchar_t *base=wcsrchr(root,L'\\');if(!base)return 1;
    int native=_wcsicmp(base+1,L"MDMNativeHost.exe")==0;*base=0;
    if(wcslen(root)>30000)return 1;
    swprintf(python,32768,L"%ls\\runtime\\%ls",root,native?L"python.exe":L"pythonw.exe");
    swprintf(script,32768,L"%ls\\app\\mdm.py",root);
    wchar_t *line=calloc(65536,sizeof(wchar_t));if(!line)return 1;
    append_quoted(line,python);append_quoted(line,L"-X");append_quoted(line,L"utf8");append_quoted(line,script);
    if(native)append_quoted(line,L"--native");
    else {
        int argc=0;LPWSTR *argv=CommandLineToArgvW(GetCommandLineW(),&argc);
        for(int i=1;i<argc;i++) {
            if(wcslen(line)+2*wcslen(argv[i])+4>=32760){LocalFree(argv);free(line);return 1;}
            append_quoted(line,argv[i]);
        }
        LocalFree(argv);
    }
    STARTUPINFOW si={0};si.cb=sizeof(si);si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    if(native){si.dwFlags|=STARTF_USESTDHANDLES;si.hStdInput=GetStdHandle(STD_INPUT_HANDLE);si.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);si.hStdError=GetStdHandle(STD_ERROR_HANDLE);}
    if(native){SetHandleInformation(si.hStdInput,HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT);SetHandleInformation(si.hStdOutput,HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT);SetHandleInformation(si.hStdError,HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT);}
    PROCESS_INFORMATION pi={0};
    BOOL ok=CreateProcessW(python,line,NULL,NULL,native,CREATE_NO_WINDOW,NULL,root,&si,&pi);
    free(line);
    if(!ok){if(!native)MessageBoxW(NULL,L"MDM could not start. Run the MDM Windows installer again to repair its private runtime.",L"Mezba Download Manager",MB_OK|MB_ICONERROR);return 1;}
    CloseHandle(pi.hThread);
    DWORD code=0;if(native){WaitForSingleObject(pi.hProcess,INFINITE);GetExitCodeProcess(pi.hProcess,&code);}
    CloseHandle(pi.hProcess);return (int)code;
}
