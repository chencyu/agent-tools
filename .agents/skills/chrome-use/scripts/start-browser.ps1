#Requires -Version 7
[CmdletBinding()]
param(
    [ValidateSet('Chrome', 'Edge')]
    [string]$Browser,

    [ValidateRange(1, 65535)]
    [int]$Port = 9222,

    [string]$ProfileDir,

    [string]$Executable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$browserConfigurations = @{
    Chrome = @{
        ProgIdPattern = '^Chrome'
        ProfileName = 'chrome-profile'; ExecutableName = 'chrome.exe'; InstallPath = 'Google\Chrome\Application'
        InstallRoots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LocalAppData)
    }
    Edge   = @{
        ProgIdPattern = '^MSEdge'
        ProfileName = 'msedge-profile'; ExecutableName = 'msedge.exe'; InstallPath = 'Microsoft\Edge\Application'
        InstallRoots = @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LocalAppData)
    }
}

$defaultsPath = Join-Path $PSScriptRoot 'start-browser.psd1'

function Import-ParameterDefaults {
    if (-not (Test-Path -LiteralPath $defaultsPath -PathType Leaf)) { return }

    $defaults = Import-PowerShellDataFile -LiteralPath $defaultsPath
    foreach ($name in $defaults.Keys) {
        if (-not $script:MyInvocation.MyCommand.Parameters.ContainsKey($name)) {
            throw "$defaultsPath sets '$name', which is not a parameter of $($script:MyInvocation.MyCommand.Name)."
        }
        if ($script:PSBoundParameters.ContainsKey($name)) { continue }
        # Assigning the parameter variable reruns its validation attributes
        Set-Variable -Name $name -Value $defaults[$name] -Scope Script
    }
}

function Get-SystemDefaultBrowser {
    # The shell API resolves the https handler however the current Windows build stores it
    Add-Type -Namespace Win32 -Name Shlwapi -MemberDefinition @'
[DllImport("shlwapi.dll", CharSet = CharSet.Unicode)]
public static extern int AssocQueryString(int flags, int str, string assoc, string extra, System.Text.StringBuilder outBuf, ref uint outLen);
'@
    $ASSOCF_IS_PROTOCOL = 0x1000
    $ASSOCSTR_PROGID = 20
    $progId = [System.Text.StringBuilder]::new(512)
    [uint32]$capacity = $progId.Capacity
    $null = [Win32.Shlwapi]::AssocQueryString($ASSOCF_IS_PROTOCOL, $ASSOCSTR_PROGID, 'https', $null, $progId, [ref]$capacity)

    $match = $browserConfigurations.Keys | Where-Object { "$progId" -match $browserConfigurations[$_].ProgIdPattern } | Select-Object -First 1
    if (-not $match) {
        throw "The system default browser (ProgId '$progId') is neither Chrome nor Edge. Pass -Browser, or set Browser in $defaultsPath."
    }
    return $match
}

Import-ParameterDefaults
if (-not $Browser) { $Browser = Get-SystemDefaultBrowser }

$configuration = $browserConfigurations[$Browser]
$configuration.Executables = @(
    $Executable
    (Get-Command $configuration.ExecutableName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    $configuration.InstallRoots | Where-Object { $_ } | ForEach-Object { Join-Path $_ "$($configuration.InstallPath)\$($configuration.ExecutableName)" }
)

if ([string]::IsNullOrWhiteSpace($ProfileDir)) {
    $profileRoot = Join-Path $HOME '.cache\chrome-devtools-mcp'
    $ProfileDir = Join-Path $profileRoot $configuration.ProfileName
}
$ProfileDir = [System.IO.Path]::GetFullPath($ProfileDir)
$null = New-Item -ItemType Directory -Path $ProfileDir -Force

$resolvedExecutable = $configuration.Executables |
Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
Select-Object -First 1
if (-not $resolvedExecutable) {
    throw "$Browser executable not found. Pass -Executable with its full path or add it to PATH."
}
$resolvedExecutable = (Resolve-Path -LiteralPath $resolvedExecutable).Path

function Test-DevToolsEndpoint {
    try {
        return (Invoke-WebRequest "http://127.0.0.1:$Port/json/version" -NoProxy -TimeoutSec 2 -SkipHttpErrorCheck).StatusCode -in 200..299
    }
    catch [System.Net.Http.HttpRequestException] { return $false }
    catch [System.Threading.Tasks.TaskCanceledException] { return $false }
}

function Wait-ForDevToolsEndpoint {
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-DevToolsEndpoint)) {
        if ((Get-Date) -ge $deadline) {
            throw "The browser did not serve DevTools on port $Port within 30 seconds."
        }
        Start-Sleep -Milliseconds 500
    }
}
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $process -or -not $process.CommandLine -or $process.CommandLine.IndexOf($ProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Port $Port is held by another process or browser profile. Choose another -Port and use the same port for the CLI connection."
    }

    Wait-ForDevToolsEndpoint
    "$Browser is already serving DevTools on port $Port for $ProfileDir"
    exit 0
}

Start-Process -FilePath $resolvedExecutable -ArgumentList "--remote-debugging-port=$Port", "--user-data-dir=`"$ProfileDir`"" | Out-Null

Wait-ForDevToolsEndpoint

"$Browser is serving DevTools on port $Port for $ProfileDir"
"Next: chrome-devtools start --browserUrl http://127.0.0.1:$Port"
