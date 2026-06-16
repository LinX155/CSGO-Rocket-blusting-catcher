$ErrorActionPreference = 'Stop'

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 72)
    Write-Host $Title
    Write-Host ("=" * 72)
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-AppCompatLayers {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
        'HKLM:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
    )

    $rows = @()
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $props = Get-ItemProperty -Path $root
            foreach ($prop in $props.PSObject.Properties) {
                if ($prop.Name -in 'PSPath', 'PSParentPath', 'PSChildName', 'PSDrive', 'PSProvider') {
                    continue
                }

                if ($prop.Name -match '(?i)(powershell|pwsh|cmd|terminal|codex)') {
                    $rows += [pscustomobject]@{
                        RegistryPath = $root
                        Target       = $prop.Name
                        Flags        = $prop.Value
                    }
                }
            }
        }
    }

    return $rows
}

function Get-GlobalRunAsAdminLayers {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
        'HKLM:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
    )

    $rows = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) {
            continue
        }

        $props = Get-ItemProperty -Path $root
        foreach ($prop in $props.PSObject.Properties) {
            if ($prop.Name -in 'PSPath', 'PSParentPath', 'PSChildName', 'PSDrive', 'PSProvider') {
                continue
            }

            if ($prop.Value -match '(^|\s)RUNASADMIN(\s|$)') {
                $rows += [pscustomobject]@{
                    RegistryPath = $root
                    Target       = $prop.Name
                    Flags        = $prop.Value
                }
            }
        }
    }

    return $rows
}

function Get-CandidateCommands {
    $names = @('powershell.exe', 'pwsh.exe', 'cmd.exe', 'wt.exe')
    $rows = @()

    foreach ($name in $names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $item = Get-Item $cmd.Source
            $rows += [pscustomobject]@{
                Name         = $name
                Path         = $cmd.Source
                Exists       = $true
                FileVersion  = $item.VersionInfo.FileVersion
                ProductName  = $item.VersionInfo.ProductName
                LastWriteUtc = $item.LastWriteTimeUtc.ToString('u')
            }
        } else {
            $rows += [pscustomobject]@{
                Name         = $name
                Path         = '<not found>'
                Exists       = $false
                FileVersion  = ''
                ProductName  = ''
                LastWriteUtc = ''
            }
        }
    }

    return $rows
}

function Get-CodexLikeProcesses {
    $rows = @()
    $patterns = '(?i)(codex|openai|chatgpt|terminal|electron)'

    foreach ($proc in Get-Process | Sort-Object ProcessName) {
        $path = $null
        try {
            $path = $proc.Path
        } catch {
            $path = $null
        }

        if ($proc.ProcessName -match $patterns -or ($path -and $path -match $patterns)) {
            $rows += [pscustomobject]@{
                ProcessName = $proc.ProcessName
                Id          = $proc.Id
                Path        = if ($path) { $path } else { '<access denied or unavailable>' }
            }
        }
    }

    return $rows
}

function Get-RequestedExecutionLevel {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return '<path missing>'
    }

    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
        $unicode = [System.Text.Encoding]::Unicode.GetString($bytes)
        $pattern = 'requestedExecutionLevel[^>]+level="(requireAdministrator|highestAvailable|asInvoker)"'

        foreach ($text in @($ascii, $unicode)) {
            $match = [regex]::Match($text, $pattern, 'IgnoreCase')
            if ($match.Success) {
                return $match.Groups[1].Value
            }
        }

        return '<not found in embedded text>'
    } catch {
        return '<read failed>'
    }
}

function Get-InterestingExecutableDetails {
    param([string[]]$Paths)

    $rows = @()
    foreach ($path in ($Paths | Where-Object { $_ -and $_ -ne '<access denied or unavailable>' } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }

        $item = Get-Item -LiteralPath $path
        $rows += [pscustomobject]@{
            Path                   = $path
            Exists                 = $true
            RequestedExecutionLevel = Get-RequestedExecutionLevel -Path $path
            FileVersion            = $item.VersionInfo.FileVersion
            ProductName            = $item.VersionInfo.ProductName
        }
    }

    return $rows
}

Write-Section "Basic Context"
[pscustomobject]@{
    Timestamp      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    UserName       = [Environment]::UserName
    MachineName    = [Environment]::MachineName
    IsAdminSession = Test-IsAdmin
    PowerShell     = $PSVersionTable.PSVersion.ToString()
    Edition        = $PSVersionTable.PSEdition
    OS             = [Environment]::OSVersion.VersionString
    ComSpec        = $env:ComSpec
    ProcessorArch  = $env:PROCESSOR_ARCHITECTURE
} | Format-List

Write-Section "Command Resolution"
Get-CandidateCommands | Format-Table -AutoSize

Write-Section "AppCompat RUNASADMIN Flags"
$layers = Get-AppCompatLayers
if ($layers.Count -gt 0) {
    $layers | Format-Table -AutoSize
} else {
    Write-Host "No matching AppCompat flags found for powershell/cmd/terminal/codex."
}

Write-Section "All RUNASADMIN Compatibility Entries"
$globalRunAs = Get-GlobalRunAsAdminLayers
if ($globalRunAs.Count -gt 0) {
    $globalRunAs | Format-Table -AutoSize
} else {
    Write-Host "No RUNASADMIN compatibility entries found anywhere in the standard AppCompat layers keys."
}

Write-Section "UAC Policies"
$policyPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
if (Test-Path $policyPath) {
    Get-ItemProperty -Path $policyPath |
        Select-Object EnableLUA, ConsentPromptBehaviorAdmin, PromptOnSecureDesktop, FilterAdministratorToken |
        Format-List
} else {
    Write-Host "UAC policy key not found."
}

Write-Section "Relevant Running Processes"
$codexLike = Get-CodexLikeProcesses
if ($codexLike.Count -gt 0) {
    $codexLike | Format-Table -AutoSize
} else {
    Write-Host "No obvious codex/openai/chatgpt/terminal/electron processes found."
}

Write-Section "Execution Level Hints"
$candidateCommandPaths = @(Get-CandidateCommands | Where-Object Exists | ForEach-Object { $_.Path })
$processPaths = @($codexLike | ForEach-Object { $_.Path })
$interesting = Get-InterestingExecutableDetails -Paths ($candidateCommandPaths + $processPaths)
if ($interesting.Count -gt 0) {
    $interesting | Format-Table -AutoSize
} else {
    Write-Host "No executable details collected."
}

Write-Section "Quick Interpretation"
if ($globalRunAs.Count -gt 0) {
    Write-Host "Detected RUNASADMIN compatibility flags in AppCompat. This is a strong candidate for Windows error 740."
    Write-Host "Check the listed Target paths and remove 'Run this program as an administrator' from Compatibility settings."
} elseif (($interesting | Where-Object { $_.RequestedExecutionLevel -eq 'requireAdministrator' }).Count -gt 0) {
    Write-Host "At least one relevant executable advertises requireAdministrator in its manifest."
    Write-Host "A non-admin Codex session cannot spawn that executable directly, which maps closely to Windows error 740."
} elseif (-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
    Write-Host "powershell.exe is not resolving normally. Shell lookup may be broken on this machine."
} else {
    Write-Host "No obvious RUNASADMIN flag was found. The next likely causes are:"
    Write-Host "1. Codex is launching an intermediate helper executable that requires elevation."
    Write-Host "2. A wrapper or shortcut in the launch chain has a hidden Run as administrator setting."
    Write-Host "3. Corporate security policy is forcing elevation for spawned shells."
}

Write-Section "Next Step"
Write-Host "Send the full output back here, and I can help pinpoint the exact blocker."
