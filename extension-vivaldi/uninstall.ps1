param([switch]$CleanGenerated, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'installer_support.ps1')
$manifestPath = Join-Path $PSScriptRoot '.runtime\com.ytdl.vivaldi.json'
$planPath = Join-Path $PSScriptRoot '.runtime\registration-plan.json'
$registryPaths = @(Get-BrowserRegistryPaths)
if (Test-Path -LiteralPath $planPath) {
    $recorded = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    foreach ($path in $recorded) {
        if ($path -notmatch '^Software\\[A-Za-z0-9 _\.\\-]+\\NativeMessagingHosts\\com\.ytdl\.vivaldi$' -or $path.Contains('..')) {
            throw "Invalid recorded registry path: $path"
        }
    }
    $registryPaths = @($registryPaths + $recorded | Select-Object -Unique)
}

# Remove only entries that still belong to this installation.
foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
    $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
    try {
        foreach ($path in $registryPaths) {
            $key = $registry.OpenSubKey($path)
            $owned = $false
            if ($key) {
                try { $owned = $key.GetValue('') -eq $manifestPath }
                finally { $key.Dispose() }
            }
            if ($owned) {
                if ($DryRun) { Write-Host "Would remove $view current-user key: $path" }
                else { $registry.DeleteSubKey($path) }
            }
        }
    } finally { $registry.Dispose() }
}
if ($CleanGenerated) {
    # Restrict recursive deletion to known generated directories inside this project.
    $projectRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    foreach ($relative in @('.venv', '.runtime', 'backend\__pycache__', 'tests\__pycache__')) {
        $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $relative))
        if (-not $target.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Cleanup target is outside the project: $target"
        }
        if (Test-Path -LiteralPath $target) {
            if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing to recursively remove a directory link: $target"
            }
            if ($DryRun) { Write-Host "Would remove generated directory: $target" }
            else {
                try { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop }
                catch { throw "Could not clean $target. Remove the extension and close its engine before retrying. $($_.Exception.Message)" }
            }
        }
    }
}
if ($DryRun) { Write-Host 'Dry run complete. No registry keys or files were changed.' }
else {
    Write-Host 'Native host registration removed for this installation.'
    if ($CleanGenerated) { Write-Host 'Generated environment, runtime files, and caches removed.' }
    Write-Host 'Source code and downloaded media were preserved. The separate console application was not modified.'
    Write-Host 'Remove the browser extension as well if it is still present.'
}
