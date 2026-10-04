param([Parameter(Mandatory=$true)][string]$Uri)
$ErrorActionPreference = 'Stop'
try {
    if ($Uri.Length -gt 4096 -or $Uri -match '["\x00-\x20]') { throw 'Ungueltiger Stickatelier-Link.' }
    $atelierLink = [Uri]$Uri
    if ($atelierLink.Scheme -ne 'stickatelier' -or $atelierLink.Host -ne 'open' -or $atelierLink.AbsolutePath -notin @('', '/') -or $atelierLink.Fragment) { throw 'Ungueltiger Stickatelier-Link.' }
    if ($atelierLink.Query -notmatch '^\?url=([^&]+)$') { throw 'Ungueltiger Download-Link.' }
    $atelierDownload = [Uri][Uri]::UnescapeDataString($Matches[1])
    $atelierConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($atelierDownload.Scheme -notin @('http', 'https') -or $atelierDownload.UserInfo -or $atelierDownload.Fragment -or $atelierDownload.GetLeftPart([UriPartial]::Authority) -ne $atelierConfig.origin) { throw 'Dieser Stickatelier-Server wurde nicht eingerichtet. Einrichtungspaket von der verwendeten Adresse erneut installieren.' }
    if ($atelierDownload.AbsolutePath -ne '/api/creator-file' -or $atelierDownload.Query -notmatch '^\?token=[0-9a-f]{64}$') { throw 'Ungueltige Dateiabfrage.' }
    if (-not (Test-Path -LiteralPath $atelierConfig.executable -PathType Leaf) -or [IO.Path]::GetExtension($atelierConfig.executable) -ne '.exe') { throw 'Creator wurde nicht gefunden. Bitte die Einrichtung mit dem richtigen EXE-Pfad wiederholen.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $atelierRequest = [Net.HttpWebRequest]::Create($atelierDownload)
    $atelierRequest.AllowAutoRedirect = $false
    $atelierRequest.Timeout = 30000
    $atelierRequest.ReadWriteTimeout = 30000
    $atelierResponse = $atelierRequest.GetResponse()
    try {
        if ([int]$atelierResponse.StatusCode -ne 200 -or $atelierResponse.ContentType -notlike 'image/png*') { throw 'PNG konnte nicht geladen werden. In Stickatelier erneut auf Oeffnen klicken.' }
        $atelierStream = $atelierResponse.GetResponseStream()
        $atelierMemory = New-Object IO.MemoryStream
        try {
            $atelierBuffer = New-Object byte[] 65536
            while (($atelierRead = $atelierStream.Read($atelierBuffer, 0, $atelierBuffer.Length)) -gt 0) {
                if ($atelierMemory.Length+$atelierRead -gt 33554432) { throw 'Die PNG-Datei ist zu gross.' }
                $atelierMemory.Write($atelierBuffer, 0, $atelierRead)
            }
            $atelierBytes = $atelierMemory.ToArray()
        } finally { $atelierStream.Dispose(); $atelierMemory.Dispose() }
    } finally { $atelierResponse.Dispose() }
    if ($atelierBytes.Length -lt 8 -or [BitConverter]::ToString($atelierBytes,0,8) -ne '89-50-4E-47-0D-0A-1A-0A') { throw 'Die uebertragene Datei ist kein PNG.' }
    $atelierExports = Join-Path $PSScriptRoot 'Exports'
    New-Item -ItemType Directory -Path $atelierExports -Force | Out-Null
    $atelierImage = Join-Path $atelierExports ('stickatelier-'+[Guid]::NewGuid().ToString('N')+'.png')
    [IO.File]::WriteAllBytes($atelierImage, $atelierBytes)
    # Fixed executable from the user's installation; URL supplies no program or arguments.
    Start-Process -FilePath $atelierConfig.executable -ArgumentList ('"'+$atelierImage+'"') -WorkingDirectory ([IO.Path]::GetDirectoryName($atelierConfig.executable))
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show(('Creator konnte nicht geoeffnet werden. Bitte in Stickatelier erneut versuchen. Details: '+$_.Exception.Message),'Stickatelier') | Out-Null
}
