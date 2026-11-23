param([string]$InstallDirectory = $PSScriptRoot)

$ErrorActionPreference = 'Stop'

function Install-StagedPackage {
    param([string]$Install, [string]$Package, [string]$Backup)

    $files = @('BankBridgeNext.exe', '_internal', 'BankBridgeNext.build')
    foreach ($directory in @($Install, $Package)) {
        if (-not (Test-Path -LiteralPath (Join-Path $directory 'BankBridgeNext.exe') -PathType Leaf) -or
            -not (Test-Path -LiteralPath (Join-Path $directory '_internal') -PathType Container)) {
            throw 'The BankBridgeNext executable or its _internal folder is missing.'
        }
    }

    [void](New-Item -ItemType Directory -Path $Backup)
    $saved = @()
    $installed = @()
    try {
        foreach ($name in $files) {
            $path = Join-Path $Install $name
            if (Test-Path -LiteralPath $path) {
                Move-Item -LiteralPath $path -Destination $Backup
                $saved += $name
            }
        }
        foreach ($name in $files) {
            Move-Item -LiteralPath (Join-Path $Package $name) -Destination $Install
            $installed += $name
        }
    } catch {
        $updateError = $_
        try {
            foreach ($name in $installed) {
                Move-Item -LiteralPath (Join-Path $Install $name) -Destination $Package
            }
            foreach ($name in $saved) {
                Move-Item -LiteralPath (Join-Path $Backup $name) -Destination $Install
            }
        } catch {
            throw "Update and automatic recovery failed. Previous files are available in $Backup. $($_.Exception.Message)"
        }
        throw $updateError
    }
}

function Install-WithRollingBackup {
    param([string]$Install, [string]$Package)

    $backup = Join-Path $Install '.bankbridge-previous'
    $retired = $null
    if (Test-Path -LiteralPath $backup) {
        $existing = Get-Item -LiteralPath $backup -Force
        $contents = @(Get-ChildItem -LiteralPath $backup -Force)
        $marker = $contents | Where-Object Name -eq '.bankbridge-updater-backup'
        $unexpected = $contents | Where-Object {
            $_.Name -notin @('.bankbridge-updater-backup', 'BankBridgeNext.exe', '_internal', 'BankBridgeNext.build')
        }
        if (-not $existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not $marker -or $marker.PSIsContainer -or $unexpected) {
            throw "The rollback location contains files the updater does not manage: $backup"
        }
        $retired = Join-Path $Install ('.bankbridge-retired-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath $backup -Destination $retired
    }

    try {
        Install-StagedPackage -Install $Install -Package $Package -Backup $backup
    } catch {
        if ((Test-Path -LiteralPath $backup) -and -not @(Get-ChildItem -LiteralPath $backup -Force).Count) {
            Remove-Item -LiteralPath $backup
        }
        if ($retired -and -not (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $retired -Destination $backup
        } elseif ($retired) {
            Write-Warning "An earlier rollback copy is still available in $retired."
        }
        throw
    }

    Set-Content -LiteralPath (Join-Path $backup '.bankbridge-updater-backup') -Value 'BankBridgeNext'
    if ($retired) {
        try {
            Remove-Item -LiteralPath $retired -Recurse -Force
        } catch {
            Write-Warning "The update succeeded, but an earlier rollback copy could not be removed: $retired"
        }
    }
    return $backup
}

function Update-BankBridgeNext {
    param([string]$Directory)

    $install = (Resolve-Path -LiteralPath $Directory).Path
    if ((Test-Path -LiteralPath (Join-Path $install '.git')) -or
        -not (Test-Path -LiteralPath (Join-Path $install 'BankBridgeNext.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $install '_internal') -PathType Container)) {
        throw 'Put both updater files beside BankBridgeNext.exe in the extracted portable build.'
    }
    if (-not (Get-Command gh.exe -CommandType Application -ErrorAction SilentlyContinue)) {
        throw 'Install GitHub CLI, then run gh auth login once before using this updater.'
    }

    $lockPath = Join-Path $install 'BankBridgeNext.update.lock'
    $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    $stage = $null
    try {
        if (Get-Process -Name BankBridgeNext -ErrorAction SilentlyContinue) {
            throw 'Close BankBridgeNext before updating.'
        }

        $repo = 'adkhaann/BankBridge-Next'
        $runs = gh run list --repo $repo --workflow regression.yml --branch pdf-to-qbo --event push --status success --limit 1 --json databaseId,headSha
        if ($LASTEXITCODE -ne 0) { throw 'Could not check GitHub. Run gh auth login if GitHub CLI is not signed in.' }
        $latest = @($runs | ConvertFrom-Json)[0]
        if (-not $latest.databaseId -or $latest.headSha -notmatch '^[a-f0-9]{40}$') {
            throw 'No passing development build was found.'
        }

        $version = Join-Path $install 'BankBridgeNext.build'
        if ((Test-Path -LiteralPath $version) -and (Get-Content -LiteralPath $version -Raw).Trim() -eq $latest.headSha) {
            Write-Host 'BankBridgeNext is already up to date.'
            return
        }

        $parent = Split-Path -Parent $install
        $stage = Join-Path $parent ('.BankBridgeNext-update-' + [guid]::NewGuid().ToString('N'))
        [void](New-Item -ItemType Directory -Path $stage)
        Write-Host "Downloading tested build $($latest.headSha.Substring(0, 7))..."
        gh run download $latest.databaseId --repo $repo --name BankBridgeNext-Windows-x64 --dir $stage
        if ($LASTEXITCODE -ne 0) { throw 'The build could not be downloaded. Your current copy is still installed.' }

        $marker = Join-Path $stage 'BankBridgeNext.build'
        if (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or
            (Get-Content -LiteralPath $marker -Raw).Trim() -ne $latest.headSha) {
            throw 'The package build marker does not match the passing GitHub run.'
        }
        if (Get-Process -Name BankBridgeNext -ErrorAction SilentlyContinue) {
            throw 'BankBridgeNext opened during download. Close it and run the update again.'
        }

        $backup = Install-WithRollingBackup -Install $install -Package $stage
        Write-Host "Update complete. Previous application files: $backup"
    } finally {
        $lock.Dispose()
        if ($stage -and (Test-Path -LiteralPath $stage)) {
            Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Update-BankBridgeNext -Directory $InstallDirectory
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}
