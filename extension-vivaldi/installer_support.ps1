# Return validated vendor paths used to register this host for Chromium browsers.
function Get-BrowserRegistryPaths {
    param([string[]]$AdditionalBrowserRegistryPaths = @())
    $configuration = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'browsers.json') -Raw | ConvertFrom-Json
    $prefixes = @($configuration.registryPrefixes) + @($AdditionalBrowserRegistryPaths)
    foreach ($prefix in ($prefixes | Select-Object -Unique)) {
        if ($prefix -notmatch '^[A-Za-z0-9 _.-]+(\\[A-Za-z0-9 _.-]+)*$' -or $prefix.Contains('..')) {
            throw "Invalid browser registry prefix: $prefix"
        }
        "Software\$prefix\NativeMessagingHosts\com.ytdl.vivaldi"
    }
}

# Derive the stable Chromium extension ID from the public manifest key.
function Get-ExtensionId {
    param([string]$ManifestPath)
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash([Convert]::FromBase64String($manifest.key)) }
    finally { $sha.Dispose() }
    -join ($digest[0..15] | ForEach-Object { [char](97 + ($_ -shr 4)); [char](97 + ($_ -band 15)) })
}
