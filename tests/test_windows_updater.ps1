$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../windows/Update-BankBridgeNext.ps1"

function New-TestPackage {
    param([string]$Directory, [string]$Version)
    [void](New-Item -ItemType Directory -Path (Join-Path $Directory '_internal') -Force)
    Set-Content -LiteralPath (Join-Path $Directory 'BankBridgeNext.exe') -Value $Version
    Set-Content -LiteralPath (Join-Path $Directory 'BankBridgeNext.build') -Value $Version
    Set-Content -LiteralPath (Join-Path $Directory '_internal/engine.py') -Value $Version
}

function Assert-Package {
    param([string]$Directory, [string]$Version)
    foreach ($name in @('BankBridgeNext.exe', 'BankBridgeNext.build', '_internal/engine.py')) {
        if ((Get-Content -LiteralPath (Join-Path $Directory $name) -Raw).Trim() -ne $Version) {
            throw "Unexpected content for $Directory/$name."
        }
    }
}

$root = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
$install = Join-Path $root 'Install with spaces'
$stage = Join-Path $root 'stage'
try {
    New-TestPackage -Directory $install -Version old
    New-TestPackage -Directory $stage -Version new
    Set-Content -LiteralPath (Join-Path $install 'local-notes.txt') -Value local

    $backup = Install-WithRollingBackup -Install $install -Package $stage
    Assert-Package -Directory $install -Version new
    Assert-Package -Directory $backup -Version old
    if (-not (Test-Path -LiteralPath (Join-Path $install 'local-notes.txt'))) {
        throw 'Unrelated local file was lost.'
    }

    New-TestPackage -Directory $stage -Version newer
    $nextBackup = Install-WithRollingBackup -Install $install -Package $stage
    if ($nextBackup -ne $backup) { throw 'The backup folder changed.' }
    Assert-Package -Directory $install -Version newer
    Assert-Package -Directory $backup -Version new
    if (Get-ChildItem -LiteralPath $install -Filter '.bankbridge-retired-*' -Force) {
        throw 'A superseded rollback folder was retained.'
    }

    New-TestPackage -Directory $stage -Version latest
    function Move-Item {
        param([string]$LiteralPath, [string]$Destination)
        if ($LiteralPath -eq (Join-Path $stage '_internal') -and $Destination -eq $install) {
            throw 'Simulated replacement failure.'
        }
        Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination
    }
    $failed = $false
    try {
        Install-WithRollingBackup -Install $install -Package $stage
    } catch {
        if ($_.Exception.Message -ne 'Simulated replacement failure.') { throw }
        $failed = $true
    }
    if (-not $failed) { throw 'The simulated failure should have been reported.' }
    Assert-Package -Directory $install -Version newer
    Assert-Package -Directory $stage -Version latest
    Assert-Package -Directory $backup -Version new

    $unrelated = Join-Path $backup 'unrelated.txt'
    Set-Content -LiteralPath $unrelated -Value local
    $failed = $false
    try {
        Install-WithRollingBackup -Install $install -Package $stage
    } catch {
        if ($_.Exception.Message -notlike '*does not manage*') { throw }
        $failed = $true
    }
    if (-not $failed -or -not (Test-Path -LiteralPath $unrelated)) {
        throw 'An unrecognized file in the backup was not protected.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $install 'local-notes.txt'))) {
        throw 'Unrelated local file was lost.'
    }
    Write-Host 'Windows updater replacement and rollback passed.'
} finally {
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
