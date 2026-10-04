$ErrorActionPreference = 'Stop'
$atelierKey = 'HKCU:\Software\Classes\stickatelier'
if ((Test-Path -LiteralPath $atelierKey) -and (Get-Item -LiteralPath $atelierKey).GetValue('') -eq 'URL:Stickatelier Creator Bridge') {
    [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('Software\Classes\stickatelier', $false)
}
Write-Host 'Stickatelier-Link deaktiviert. Gespeicherte PNG-Dateien bleiben erhalten.'
