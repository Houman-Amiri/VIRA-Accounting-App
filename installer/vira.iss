; V.I.R.A — Inno Setup 6 installer (Phase 8 §1)
; Windows-native, no Docker/containers. Compiled in GitHub Actions with:
;   iscc installer/vira.iss /DAppVersion=X.Y.Z
;
; Mandated wizard: welcome → license → «مسیر نصب» (select where to install,
; DisableDirPage=no) → additional tasks → install → finish. The chosen InstallDir
; is recorded under HKLM/HKCU \SOFTWARE\VIRA\InstallDir for the updater and
; uninstaller. User data lives ONLY under %LOCALAPPDATA%\VIRA and is never
; removed unless the user explicitly opts in on uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppSource
  #define AppSource "..\dist-release\app"
#endif

#ifdef PrivateSourceCI
  #ifndef PrivateSourceAnchor
    #error PrivateSourceAnchor is required for the isolated private installer
  #endif
  #ifndef PrivateSourceProfile
    #error PrivateSourceProfile is required for the isolated private installer
  #endif
  #define AppName "VIRA PRIVATE SOURCE CI"
  #define AppExeName "python\python.exe"
  #define LaunchWorkingDir PrivateSourceProfile
  #define RegistryKey "SOFTWARE\VIRA\PrivateSourceCI"
#else
  #define AppName "V.I.R.A"
  #define AppExeName "start_vira.cmd"
  #define LaunchWorkingDir "{app}"
  #define RegistryKey "SOFTWARE\VIRA"
#endif
#define AppPublisher "VIRA"

[Setup]
#ifdef PrivateSourceCI
AppId={{CB072AD0-8D63-49D3-9839-1DE745D62CA4}
#else
AppId={{B7E4C2A1-9F3D-4E8B-A6C5-1D2E3F405968}
#endif
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\VIRA
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
; license page is optional per Phase 8 §1 — add LicenseFile=..\docs\LICENSE.txt when a license ships
OutputDir=Output
OutputBaseFilename=VIRA-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
#ifdef PrivateSourceCI
; Keep generated uninstaller code OUTSIDE the fully manifested app payload.
UninstallFilesDir={#PrivateSourceProfile}\VIRA\private-native-installed\uninstaller
#endif
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
; silent install for CI smoke tests: VIRA-Setup-x.y.z.exe /VERYSILENT /DIR=<temp>
SetupLogging=yes

[Languages]
; Farsi wizard translation when the Inno installation ships it (6.x does);
; the mandated «مسیر نصب» page is always Persian via [Messages] below.
#ifexist "compiler:Languages\Farsi.isl"
Name: "persian"; MessagesFile: "compiler:Languages\Farsi.isl"
#endif

[Messages]
SelectDirTitle=مسیر نصب
SelectDirLabel=مسیر نصب برنامه را انتخاب کنید.
SelectDirBrowseLabel=برای ادامه، روی «بعدی» کلیک کنید. اگر می‌خواهید پوشهٔ دیگری را انتخاب کنید، روی «مرور» کلیک کنید.

[Tasks]
Name: "desktopicon"; Description: "ایجاد میان‌بر در دسکتاپ"; GroupDescription: "میان‌برها:"
Name: "startmenu"; Description: "ایجاد میان‌بر در منوی استارت"; GroupDescription: "میان‌برها:"
Name: "startup"; Description: "اجرا هنگام ورود به ویندوز"; GroupDescription: "شروع خودکار:"
Name: "backupjob"; Description: "ثبت کار زمان‌بند پشتیبان‌گیری (Task Scheduler)"; GroupDescription: "نگهداری:"

[Files]
; packaged backend bundle (PyInstaller one-folder / embedded CPython)
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; updater helper (staged next to the app; also copied to %LOCALAPPDATA%\VIRA\updates)
Source: "{#AppSource}\vira-updater.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

#ifdef PrivateSourceCI
; Digest anchor is OUTSIDE the payload. Never remove state/anchor on uninstall.
Source: "{#PrivateSourceAnchor}"; DestDir: "{#PrivateSourceProfile}\VIRA\private-native-installed"; DestName: "anchor.json"; Flags: uninsneveruninstall
#endif

[InstallDelete]
; v1.0.5 incident: the old hashed bundles stayed next to the new ones, so a
; cached index.html could keep loading the previous UI. Code and SPA are
; replaced wholesale on every install/upgrade (user data is untouched — it
; lives under %LOCALAPPDATA%\VIRA).
Type: filesandordirs; Name: "{app}\static"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\backend"

[Icons]
#ifdef PrivateSourceCI
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "-I -S -B -X utf8 ""{app}\app\private_installed_source.py"""; WorkingDir: "{#LaunchWorkingDir}"
#else
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{#LaunchWorkingDir}"
#endif
#ifdef PrivateSourceCI
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "-I -S -B -X utf8 ""{app}\app\private_installed_source.py"""; WorkingDir: "{#LaunchWorkingDir}"; Tasks: desktopicon
#else
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{#LaunchWorkingDir}"; Tasks: desktopicon
#endif
#ifdef PrivateSourceCI
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "-I -S -B -X utf8 ""{app}\app\private_installed_source.py"""; WorkingDir: "{#LaunchWorkingDir}"; Tasks: startup
#else
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{#LaunchWorkingDir}"; Tasks: startup
#endif

[Registry]
; stable install location for the updater + uninstaller (§1)
Root: HKA; Subkey: "{#RegistryKey}"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "{#RegistryKey}"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
#ifdef PrivateSourceCI
Filename: "{app}\{#AppExeName}"; Parameters: "-I -S -B -X utf8 ""{app}\app\private_installed_source.py"""; WorkingDir: "{#LaunchWorkingDir}"; Description: "اجرای {#AppName}"; Flags: nowait postinstall skipifsilent
#else
Filename: "{app}\{#AppExeName}"; WorkingDir: "{#LaunchWorkingDir}"; Description: "اجرای {#AppName}"; Flags: nowait postinstall skipifsilent
#endif
#ifndef PrivateSourceCI
Filename: "schtasks.exe"; \
  Parameters: "/Create /TN ""VIRA\Backup"" /TR ""''{app}\scripts\backup_vira.ps1''"" /SC DAILY /ST 21:00 /F"; \
  StatusMsg: "ثبت کار زمان‌بند پشتیبان‌گیری..."; \
  Flags: runhidden; Tasks: backupjob
#endif

#ifndef PrivateSourceCI
[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""VIRA\Backup"" /F"; Flags: runhidden; RunOnceId: "RemoveBackupTask"
#endif

[Code]
var
  DeleteDataPage: TInputOptionWizardPage;

function InitializeSetup(): Boolean;
begin
  Result := True;
#ifdef PrivateSourceCI
  // A separate AppId/registry namespace; never touch an existing private state.
  Result := (GetEnv('GITHUB_ACTIONS') = 'true') and
    (CompareText(GetEnv('LOCALAPPDATA'), '{#PrivateSourceProfile}') = 0) and
    (Pos(Lowercase(AddBackslash(GetEnv('RUNNER_TEMP'))), Lowercase('{#PrivateSourceProfile}')) = 1) and
    not FileExists('{#PrivateSourceProfile}\VIRA\private-native-installed\anchor.json');
#endif
end;

#ifdef PrivateSourceCI
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Rec: TFindRec;
begin
  Result := '';
  if FindFirst(ExpandConstant('{app}\*'), Rec) then
  begin
    try
      repeat
        if (Rec.Name <> '.') and (Rec.Name <> '..') then
        begin
          Result := 'Private source CI requires a fresh empty selected directory.';
          Break;
        end;
      until not FindNext(Rec);
    finally
      FindClose(Rec);
    end;
  end;
end;
#endif

procedure StopRunningInstances();
var
  ResultCode: Integer;
  AppDir: String;
  Q: String;
  Script: String;
begin
  // The app is started by the user (launcher window); a running interpreter
  // locks python.exe/*.pyd so the upgrade could not replace them (Inno would
  // then require a reboot). Only processes that live inside {app} are stopped.
  AppDir := ExpandConstant('{app}');
  Q := Chr(39);  // single quote
  Script := 'Get-CimInstance Win32_Process | Where-Object { ' +
            '(($_.Name -eq ' + Q + 'python.exe' + Q + ') -or ($_.Name -eq ' + Q + 'pythonw.exe' + Q + ')) -and ' +
            '($_.ExecutablePath -like ' + Q + AppDir + '\*' + Q + ') } | ' +
            'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; ' +
            'Get-CimInstance Win32_Process -Filter ' + Q + 'Name=' + Q + Q + 'cmd.exe' + Q + Q + Q + ' | ' +
            'Where-Object { $_.CommandLine -like ' + Q + '*' + AppDir + '\start_vira.cmd*' + Q + ' } | ' +
            'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }';
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "' + Script + '"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(700);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
#ifndef PrivateSourceCI
  if CurStep = ssInstall then
    StopRunningInstances;
#endif
end;

function InitializeUninstall(): Boolean;

begin
#ifdef PrivateSourceCI
  Result := True;
#else
  // §1: user data is NEVER deleted by default — explicit opt-in only
  DeleteDataPage := CreateInputOptionPage(wpWelcome,
    'داده‌های برنامه',
    'حذف داده‌های برنامه',
    'داده‌ها (پایگاه‌داده، رسیدها، کلیدها، پشتیبان‌ها) در %LOCALAPPDATA%\VIRA نگهداری می‌شوند و به‌طور پیش‌فرض حذف نمی‌شوند.',
    False, False);
  DeleteDataPage.Add('حذف داده‌های برنامه (غیرقابل بازگشت)');
  DeleteDataPage.Values[0] := False;
  Result := True;
#endif
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
#ifndef PrivateSourceCI
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\VIRA');
    if (DeleteDataPage <> nil) and DeleteDataPage.Values[0] then
    begin
      if MsgBox('داده‌های برنامه برای همیشه حذف شوند؟', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end
    else
      Log('Keeping user data at ' + DataDir);
  end;
#else
  Log('Private source uninstall preserves ALL private and ordinary user data.');
#endif
end;
