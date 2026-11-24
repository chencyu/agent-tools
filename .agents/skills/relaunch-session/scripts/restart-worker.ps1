# Started hidden by restart.ps1 so it outlives the tool call that requested the restart.
# Outcome of each run is appended to %TEMP%\relaunch-session.log as: <time> <sdk> <session id> <result> <typed line>.
# A failed trust grant adds a line whose result is TrustFailed and whose last field is the error.
# -ResumeArgs (the relaunch's arguments) and -Trust (what Get-ExtraArgTrust returned) are
# restart.ps1's base64 UTF-8 JSON string arrays.
param([string]$Sdk, [uint32]$AgentPid, [string]$SessionId, [uint32]$ToolCallPid, [switch]$ExitOnly, [string]$ResumeArgs, [string]$Trust, [string]$PromptFile, [double]$DelaySeconds)

Add-Type -Path "$PSScriptRoot\SessionConsole.cs"
. "$PSScriptRoot\$Sdk.ps1"

$log = "$env:TEMP\relaunch-session.log"

function ConvertFrom-WorkerArg([string]$Encoded) {
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Encoded)) | ConvertFrom-Json
}

# Renders one argument as PowerShell source that passes it to a native command unchanged.
function Format-PwshArg([string]$Arg) {
    if ($Arg -match '^[\w\-.:\\/=]+$') { return $Arg }
    return "'" + $Arg.Replace("'", "''") + "'"
}

function Get-RelaunchLine {
    $relaunchArgs = ConvertFrom-WorkerArg $ResumeArgs
    $command = (@($AgentCommand) + ($relaunchArgs | ForEach-Object { Format-PwshArg $_ })) -join ' '
    # The shell reads the prompt from the file and deletes the file while evaluating this argument,
    # before anything it is passed to runs; the text becomes the agent's initial prompt.
    $promptArg = if ($PromptFile) {
        $path = Format-PwshArg $PromptFile
        Format-PromptArg "`$(Get-Content -Raw -Encoding utf8 -LiteralPath $path; Remove-Item -LiteralPath $path)"
    }
    if (-not $DelaySeconds) { return "$command$promptArg" }
    # The shell itself waits, so the delay shows on screen and Ctrl+C there cancels the relaunch.
    # The prompt enters as the script block's argument, so the file is gone even if the wait is cancelled.
    $delay = $DelaySeconds.ToString([cultureinfo]::InvariantCulture)
    $announce = "Write-Host ""$AgentCommand relaunches at `$((Get-Date).AddSeconds($delay).ToString('yyyy-MM-dd HH:mm:ss'))"""
    return "& { $announce; Start-Sleep -Seconds $delay; $command @args }$promptArg"
}

$line = if ($ExitOnly) { $null } else { Get-RelaunchLine }

# Ctrl+C during the requesting tool call would record it as interrupted, so the exit waits for
# that call's process to end; the margin covers the agent recording the result after the exit.
Wait-Process -Id $ToolCallPid -ErrorAction Ignore
Start-Sleep -Milliseconds 500

# Grant-ExtraArgTrust runs as SessionConsole.Restart's afterExit: no host output, no native command.
# A grant that fails still lets the relaunch run; the agent then asks for that trust itself.
$trustItems = if ($Trust) { @(ConvertFrom-WorkerArg $Trust) }
$afterExit = if ($trustItems) {
    [Action] {
        try { Grant-ExtraArgTrust $trustItems }
        catch { Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $Sdk $SessionId TrustFailed $_" }
    }
}

$result = [SessionConsole]::Restart($AgentPid, $line, $CtrlCPresses, $CtrlCIntervalMs, $afterExit)
# Only a typed relaunch line consumes the prompt file; on every other outcome nothing will read it.
if ($PromptFile -and $result -ne [RestartResult]::Relaunched) { Remove-Item -LiteralPath $PromptFile -ErrorAction Ignore }
Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $Sdk $SessionId $result $line"
