Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "FileFunc.nsh"
!ifndef VERSION
!define VERSION "0.1.2"
!endif
!ifndef PAYLOAD
!error "Define PAYLOAD as the staged application directory"
!endif
!ifndef OUTPUT
!define OUTPUT "Mezba-Download-Manager-${VERSION}-Windows-x64-Setup.exe"
!endif
Name "Mezba Download Manager ${VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Mezba Download Manager"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
Icon "mdm.ico"
UninstallIcon "mdm.ico"
VIProductVersion "0.1.2.0"
VIAddVersionKey /LANG=1033 "ProductName" "Mezba Download Manager"
VIAddVersionKey /LANG=1033 "FileDescription" "MDM Windows installer"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "MDM source: MIT license"
!define MUI_ABORTWARNING
!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "Mezba Download Manager installed"
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\MDM.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "--updated"
!define MUI_FINISHPAGE_TEXT "MDM is ready. Use Browser setup in the app to add the companion extension. Reload an existing extension and open video pages after updates."
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Var IsUpdate
Var HadPrevious
Var InstallerMutex
Function .onInit
 ${IfNot} ${RunningX64}
  MessageBox MB_ICONSTOP "This MDM installer requires 64-bit Windows 10 or 11."
  Abort
 ${EndIf}
 ${IfNot} ${AtLeastWin10}
  MessageBox MB_ICONSTOP "MDM requires Windows 10 or later."
  Abort
 ${EndIf}
 System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\MezbaMDMInstaller") p .r0 ?e'
 StrCpy $InstallerMutex $0
 Pop $1
 ${If} $1 = 183
  MessageBox MB_ICONSTOP "Another MDM installer is already running."
  Abort
 ${EndIf}
 ${GetParameters} $0
 ${GetOptions} $0 "/UPDATE" $IsUpdate
FunctionEnd
Section "Install"
 SetShellVarContext current
 StrCpy $HadPrevious 0
 IfFileExists "$INSTDIR\app\setup_windows.py" 0 prepare_done
 DetailPrint "Saving downloads and stopping the previous download service..."
 nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\app\setup_windows.py" prepare'
 Pop $0
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "Close MDM and pause active tasks, then retry. Your current installation was kept."
  Abort
 ${EndIf}
 RMDir /r "$INSTDIR\app.previous"
 ClearErrors
 Rename "$INSTDIR\app" "$INSTDIR\app.previous"
 ${If} ${Errors}
  MessageBox MB_ICONSTOP "Could not stage this update. Close MDM progress windows and retry."
  Delete "$LOCALAPPDATA\Mezba Download Manager\State\installing.json"
  Abort
 ${EndIf}
 StrCpy $HadPrevious 1
prepare_done:
 SetOutPath "$INSTDIR"
 SetOverwrite on
 File "${PAYLOAD}/MDM.exe"
 File "${PAYLOAD}/MDMNativeHost.exe"
 SetOverwrite off
 SetOutPath "$INSTDIR\runtime"
 File /r "${PAYLOAD}/runtime/*"
 SetOverwrite on
 SetOutPath "$INSTDIR\app"
 File /r "${PAYLOAD}/app/*"
 SetOutPath "$INSTDIR"
 File "${PAYLOAD}/README.md"
 File "${PAYLOAD}/LICENSE"
 DetailPrint "Downloading and verifying media tools. First setup needs internet access."
 nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\app\setup_windows.py" finish'
 Pop $0
 ${If} $0 != 0
  nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\app\setup_windows.py" prepare'
  Pop $1
  ${If} $HadPrevious == 1
   RMDir /r "$INSTDIR\app"
   Rename "$INSTDIR\app.previous" "$INSTDIR\app"
   nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\app\setup_windows.py" recover'
   Pop $1
  ${EndIf}
  Delete "$LOCALAPPDATA\Mezba Download Manager\State\installing.json"
  MessageBox MB_ICONSTOP "Setup could not finish. Check the details above, ensure internet access, and run the installer again. An existing app was restored when available. Your downloads and settings are kept."
  Abort
 ${EndIf}
 CreateDirectory "$SMPROGRAMS\Mezba Download Manager"
 CreateShortcut "$SMPROGRAMS\Mezba Download Manager\Mezba Download Manager.lnk" "$INSTDIR\MDM.exe"
 CreateShortcut "$SMPROGRAMS\Mezba Download Manager\README.lnk" "$INSTDIR\README.md"
 CreateShortcut "$DESKTOP\Mezba Download Manager.lnk" "$INSTDIR\MDM.exe"
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "DisplayName" "Mezba Download Manager"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "DisplayVersion" "${VERSION}"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "Publisher" "Mezba Download Manager"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "DisplayIcon" "$INSTDIR\MDM.exe"
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager" "NoRepair" 1
SectionEnd
Section "Uninstall"
 SetShellVarContext current
 nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\app\setup_windows.py" unregister'
 Pop $0
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "Close MDM and its progress windows, then retry uninstalling."
  Abort
 ${EndIf}
 Delete "$DESKTOP\Mezba Download Manager.lnk"
 RMDir /r "$SMPROGRAMS\Mezba Download Manager"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MezbaDownloadManager"
 RMDir /r "$INSTDIR\app"
 RMDir /r "$INSTDIR\app.previous"
 RMDir /r "$INSTDIR\runtime"
 RMDir /r "$INSTDIR\tools"
 RMDir /r "$INSTDIR\native-hosts"
 Delete "$INSTDIR\MDM.exe"
 Delete "$INSTDIR\MDMNativeHost.exe"
 RMDir /r "$INSTDIR\components"
 Delete "$INSTDIR\README.md"
 Delete "$INSTDIR\LICENSE"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
 MessageBox MB_OK "MDM was removed. Downloads and history were kept. Remove its browser extension separately."
SectionEnd
