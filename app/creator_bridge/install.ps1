$ErrorActionPreference = 'Stop'
try {
    $atelierConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $atelierConfig.executable -PathType Leaf) -or [IO.Path]::GetExtension($atelierConfig.executable) -ne '.exe') {
        throw 'Creator wurde unter diesem Pfad nicht gefunden. Pfad in Stickatelier korrigieren und Einrichtungspaket neu herunterladen.'
    }
    $atelierKey = 'HKCU:\Software\Classes\stickatelier'
    if (Test-Path -LiteralPath $atelierKey) {
        $atelierOwner = (Get-Item -LiteralPath $atelierKey).GetValue('')
        if ($atelierOwner -ne 'URL:Stickatelier Creator Bridge') { throw 'Das Link-Protokoll stickatelier ist bereits durch eine andere Anwendung belegt.' }
    }
    $atelierFolder = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Stickatelier\CreatorBridge'
    New-Item -ItemType Directory -Path $atelierFolder -Force | Out-Null
    foreach ($atelierFile in @('open-creator.ps1', 'uninstall.ps1', 'config.json')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $atelierFile) -Destination (Join-Path $atelierFolder $atelierFile) -Force
    }
    $atelierPowerShell = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
    $atelierScript = Join-Path $atelierFolder 'open-creator.ps1'
    New-Item -Path ($atelierKey+'\shell\open\command') -Force | Out-Null
    Set-Item -LiteralPath $atelierKey -Value 'URL:Stickatelier Creator Bridge'
    New-ItemProperty -LiteralPath $atelierKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    Set-Item -LiteralPath ($atelierKey+'\shell\open\command') -Value ('"{0}" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -Uri "%1"' -f $atelierPowerShell, $atelierScript)
    Write-Host 'Einrichtung abgeschlossen. In Stickatelier jetzt "Windows-Helfer eingerichtet" aktivieren und speichern.'
    Write-Host ('Programm: '+$atelierConfig.executable)
    Write-Host ('Stickatelier: '+$atelierConfig.origin)
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
