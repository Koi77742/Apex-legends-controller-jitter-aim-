@echo off
setlocal
cd /d "%~dp0"

set "VERSION_TEMPLATE=version_info.txt"
set "VERSION_FILE=version_info.generated.txt"
for /f "delims=" %%A in ('powershell -NoProfile -Command "$chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; $bytes=New-Object byte[] 20; $rng=[Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $name=''; for($i=0; $i -lt $bytes.Length; $i++){ $name += $chars[[int]$bytes[$i] %% $chars.Length] }; $rng.Dispose(); $name"') do set "EXE_NAME=%%A"

if not defined EXE_NAME (
    echo [ERROR] Could not generate the executable name.
    pause
    exit /b 1
)

set "OUTPUT_DIR=dist"
set "OUTPUT_EXE=%OUTPUT_DIR%\%EXE_NAME%.exe"

echo [INFO] Checking environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12 and add it to PATH.
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt is missing.
    pause
    exit /b 1
)

echo [INFO] Installing pinned dependencies...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :build_error

python -m pip check
if errorlevel 1 goto :build_error

if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"
if exist "%EXE_NAME%.spec" del /q "%EXE_NAME%.spec"
if exist "%VERSION_FILE%" del /q "%VERSION_FILE%"

echo [INFO] Creating Windows metadata for %EXE_NAME%.exe...
powershell -NoProfile -Command "$name=$env:EXE_NAME; $template=[IO.File]::ReadAllText((Join-Path (Get-Location) $env:VERSION_TEMPLATE)); $content=$template.Replace('__EXE_NAME__',$name); [IO.File]::WriteAllText((Join-Path (Get-Location) $env:VERSION_FILE),$content,(New-Object Text.UTF8Encoding($false)))"
if errorlevel 1 goto :build_error
powershell -NoProfile -Command "$content=[IO.File]::ReadAllText((Join-Path (Get-Location) $env:VERSION_FILE)); if ($content.Contains('__EXE_NAME__')) { Write-Error 'Generated metadata still contains an unresolved name placeholder.'; exit 1 }"
if errorlevel 1 goto :build_error

echo [INFO] Building standalone one-file application...
python -m PyInstaller --noconfirm --onefile --windowed ^
--icon="pfp.ico" ^
--name="%EXE_NAME%" ^
--distpath="%OUTPUT_DIR%" ^
--version-file="%VERSION_FILE%" ^
--hidden-import="_cffi_backend" ^
--hidden-import="pygame._sdl2.controller" ^
--optimize=2 ^
--noupx ^
--clean ^
skp.py
if errorlevel 1 goto :build_error

if not exist "%OUTPUT_EXE%" goto :build_error

powershell -NoProfile -Command "$expected=$env:EXE_NAME; $info=(Get-Item -LiteralPath $env:OUTPUT_EXE).VersionInfo; $fields=@('CompanyName','FileDescription','InternalName','ProductName'); foreach ($field in $fields) { if ($info.$field -ne $expected) { Write-Error ($field + ' does not match the executable name.'); exit 1 } }; if ($info.OriginalFilename -ne ($expected + '.exe')) { Write-Error 'OriginalFilename does not match the executable name.'; exit 1 }"
if errorlevel 1 goto :build_error

if exist "%EXE_NAME%.spec" del /q "%EXE_NAME%.spec"
if exist "%VERSION_FILE%" del /q "%VERSION_FILE%"

powershell -NoProfile -Command "$exe = '%OUTPUT_EXE%'; $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash; $signature = (Get-AuthenticodeSignature -LiteralPath $exe).Status; Write-Host ('[SECURITY] SHA-256: ' + $hash); Write-Host ('[SECURITY] Signature: ' + $signature)"
if errorlevel 1 goto :build_error

echo [INFO] Removing temporary build files...
if exist "build" rd /s /q "build"

echo [SUCCESS] Standalone executable: %OUTPUT_EXE%
echo [INFO] Run: %OUTPUT_EXE%
echo [SECURITY] Sign %EXE_NAME%.exe with a trusted code-signing certificate before distribution.
pause
exit /b 0

:build_error
if exist "%VERSION_FILE%" del /q "%VERSION_FILE%"
if exist "%EXE_NAME%.spec" del /q "%EXE_NAME%.spec"
echo [ERROR] Build failed. Review the messages above.
pause
exit /b 1
