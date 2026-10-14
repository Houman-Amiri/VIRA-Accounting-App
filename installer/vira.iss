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

#define AppName "V.I.R.A"
#define AppExeName "start_vira.cmd"
#define AppPublisher "VIRA"

[Setup]
AppId={{B7E4C2A1-9F3D-4E8B-A6C5-1D2E3F405968}
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

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: startup

[Registry]
; stable install location for the updater + uninstaller (§1)
Root: HKA; Subkey: "SOFTWARE\VIRA"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "SOFTWARE\VIRA"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExeName}"; Description: "اجرای {#AppName}"; Flags: nowait postinstall skipifsilent
Filename: "schtasks.exe"; \
  Parameters: "/Create /TN ""VIRA\Backup"" /TR ""''{app}\scripts\backup_vira.ps1''"" /SC DAILY /ST 21:00 /F"; \
  StatusMsg: "ثبت کار زمان‌بند پشتیبان‌گیری..."; \
  Flags: runhidden; Tasks: backupjob

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""VIRA\Backup"" /F"; Flags: runhidden; RunOnceId: "RemoveBackupTask"

[Code]
var
  DeleteDataPage: TInputOptionWizardPage;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure InitializeUninstall();
begin
  // §1: user data is NEVER deleted by default — explicit opt-in only
  DeleteDataPage := CreateInputOptionPage(wpWelcome,
    'داده‌های برنامه',
    'حذف داده‌های برنامه',
    'داده‌ها (پایگاه‌داده، رسیدها، کلیدها، پشتیبان‌ها) در %LOCALAPPDATA%\VIRA نگهداری می‌شوند و به‌طور پیش‌فرض حذف نمی‌شوند.',
    False, False);
  DeleteDataPage.Add('حذف داده‌های برنامه (غیرقابل بازگشت)');
  DeleteDataPage.Values[0] := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
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
end;
