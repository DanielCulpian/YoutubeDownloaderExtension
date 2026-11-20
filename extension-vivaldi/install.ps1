param(
    [Alias('SoloPreparar')][switch]$PrepareOnly,
    [Alias('OmitirDependencias')][switch]$SkipDependencies,
    [string[]]$AdditionalBrowserRegistryPaths = @()
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'installer_support.ps1')
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtimePath = Join-Path $projectRoot '.runtime'
$utf8 = New-Object Text.UTF8Encoding($false)
$registryPaths = @(Get-BrowserRegistryPaths -AdditionalBrowserRegistryPaths $AdditionalBrowserRegistryPaths)
$previousPlan = Join-Path $runtimePath 'registration-plan.json'
# Preserve previously configured fork locations when installing another update.
if (Test-Path -LiteralPath $previousPlan) {
    $previousPaths = Get-Content -LiteralPath $previousPlan -Raw | ConvertFrom-Json
    foreach ($recordedPath in $previousPaths) {
        $recordedMatch = [regex]::Match($recordedPath, '^Software\\(.+)\\NativeMessagingHosts\\com\.ytdl\.vivaldi$')
        if (-not $recordedMatch.Success) {
            throw "Invalid previous registration path: $recordedPath"
        }
        $registryPaths += @(Get-BrowserRegistryPaths -AdditionalBrowserRegistryPaths @($recordedMatch.Groups[1].Value))
    }
    $registryPaths = @($registryPaths | Select-Object -Unique)
}

# Create an isolated runtime without changing the user's PATH or system Python.
if (-not $SkipDependencies) {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & python -m venv (Join-Path $projectRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the environment. Install Python 3.11 or newer.' }
    }
    & $pythonPath -m pip install -U -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your Internet connection.' }
    & $pythonPath (Join-Path $projectRoot 'backend\check_environment.py')
    if ($LASTEXITCODE -ne 0) { throw 'A required dependency, Tkinter, or JavaScript runtime is missing.' }
}

# Generate the native launcher and allow only the stable extension origin.
$extensionId = Get-ExtensionId (Join-Path $projectRoot 'extension\manifest.json')
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$launcherPath = Join-Path $runtimePath 'host.cmd'
$launcher = '@echo off' + "`r`n" + '"%~dp0..\.venv\Scripts\python.exe" -u "%~dp0..\backend\native_host.py" %*' + "`r`n"
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::ASCII)
$manifestPath = Join-Path $runtimePath 'com.ytdl.vivaldi.json'
$nativeManifest = [ordered]@{
    name = 'com.ytdl.vivaldi'
    description = 'YouTube Downloader local native messaging host'
    path = $launcherPath
    type = 'stdio'
    allowed_origins = @("chrome-extension://$extensionId/")
}
[IO.File]::WriteAllText($manifestPath, ($nativeManifest | ConvertTo-Json -Depth 4), $utf8)
[IO.File]::WriteAllText((Join-Path $runtimePath 'registration-plan.json'),
    (ConvertTo-Json -InputObject @($registryPaths)), $utf8)

# Register both Windows registry views for the current user only.
if (-not $PrepareOnly) {
    foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
        $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
        try {
            foreach ($path in $registryPaths) {
                $key = $registry.CreateSubKey($path)
                try { $key.SetValue('', $manifestPath, [Microsoft.Win32.RegistryValueKind]::String) }
                finally { $key.Dispose() }
            }
        } finally { $registry.Dispose() }
    }
}
Write-Host "Native host prepared. Extension ID: $extensionId" -ForegroundColor Green
if ($PrepareOnly) { Write-Host 'Prepare-only mode: no registry entries were changed.' }
else {
    Write-Host 'Open your browser extension manager, enable Developer mode, and choose Load unpacked.'
    Write-Host ('Select this directory: ' + (Join-Path $projectRoot 'extension'))
    Write-Host 'Then reload YouTube and open YouTube Downloader.'
}
