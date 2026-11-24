# Run from an agent's tool shell to restart that session with its launch args. <Sdk> names the
# agent (claude or copilot); it is never detected. Returns at once; once the tool call running this
# script has finished, the agent exits gracefully and the same command, resuming this session, is
# typed into the PowerShell prompt that launched it. -ExtraArgs are options appended to the launch
# args; the agent's own parser resolves any repeats. -Prompt becomes the resumed session's first
# user message. -DelaySeconds makes the shell wait that long between the exit and the relaunch.
# -ExitOnly stops after the graceful exit.
param(
    [Parameter(Mandatory, Position = 0)][ValidateSet('claude', 'copilot')][string]$Sdk,
    [switch]$ExitOnly, [string[]]$ExtraArgs, [string]$Prompt, [ValidateRange('NonNegative')][double]$DelaySeconds
)

if ($ExitOnly -and ($ExtraArgs -or $Prompt -or $DelaySeconds)) { throw '-ExtraArgs, -Prompt, and -DelaySeconds shape the relaunch; they cannot be combined with -ExitOnly.' }

. "$PSScriptRoot\$Sdk.ps1"
Add-Type -Path "$PSScriptRoot\SessionConsole.cs"

# Index one past the values the agent's argument parser would bind to the option at $Start.
function Get-OptionEnd([string[]]$Tokens, [int]$Start, [string]$Kind) {
    $end = $Start + 1
    $takesValue = { $end -lt $Tokens.Count -and -not $Tokens[$end].StartsWith('-') }
    switch ($Kind) {
        'required' { if ($end -lt $Tokens.Count) { $end++ } }
        'optional' { if (& $takesValue) { $end++ } }
        'variadic' { while (& $takesValue) { $end++ } }
    }
    return $end
}

# What one option token sets: canonical names, the arity of the words after it, and the value it
# carries itself ($null if none). Both parsers accept -xVALUE and bundled short flags -xy; those
# are split only when the whole token is no spelling of its own (claude's -d2e is one).
function Read-OptionToken([string]$Token, [hashtable]$Table, [string]$Exe) {
    $name, $inlineValue = $Token -split '=', 2
    $option = Resolve-Option $Table $name $Exe
    if ($option) { return @{ Names = @($option.Name); Kind = $option.Kind; Value = $inlineValue } }
    if ($Token -match '^-(\w)(.+)$') {
        $attached = $Matches[2]
        $short = Resolve-Option $Table "-$($Matches[1])" $Exe
        if ($short -and $short.Kind -ne 'none') { return @{ Names = @($short.Name); Kind = $short.Kind; Value = $attached } }
        if ($short) {
            $names = foreach ($char in $Token.Substring(1).ToCharArray()) { (Resolve-Option $Table "-$char" $Exe)?.Name ?? "-$char" }
            return @{ Names = @($names); Kind = 'none'; Value = $null }
        }
    }
    return @{ Names = @($name); Kind = $UnknownOptionKind; Value = $inlineValue }
}

# The tokens as the parser binds them: each group is an option with its values, or a positional,
# and everything after `--` is one positional group.
function Get-ArgGroups([string[]]$Tokens, [hashtable]$Table, [string]$Exe) {
    $i = 0
    while ($i -lt $Tokens.Count) {
        $token = $Tokens[$i]
        if ($token -eq '--' -or -not $token.StartsWith('-')) {
            $end = if ($token -eq '--') { $Tokens.Count } else { $i + 1 }
            @{ Positional = $true; Tokens = $Tokens[$i..($end - 1)] }
            $i = $end
            continue
        }
        $read = Read-OptionToken $token $Table $Exe
        # An inline value fills a single-value option; a variadic one goes on taking words.
        $kind = if ($null -ne $read.Value -and $read.Kind -ne 'variadic') { 'none' } else { $read.Kind }
        $end = Get-OptionEnd $Tokens $i $kind
        $values = @(if ($null -ne $read.Value) { $read.Value }) + @($Tokens | Select-Object -Skip ($i + 1) -First ($end - $i - 1))
        @{ Positional = $false; Names = $read.Names; Kind = $read.Kind; Values = $values; Tokens = $Tokens[$i..($end - 1)] }
        $i = $end
    }
}

# The launch args minus what chose or seeded the original conversation. Positional args are the
# initial prompt (claude) or a subcommand (copilot), neither of which belongs in a resume.
function Get-KeptLaunchArgs([string[]]$LaunchArgs, [hashtable]$Table, [string]$Exe) {
    foreach ($group in Get-ArgGroups $LaunchArgs $Table $Exe) {
        if ($group.Positional -or $group.Names.Where({ $_ -in $SessionSelectors })) { continue }
        $group.Tokens
    }
}

# Throws on any extra arg that would not be a relaunch option: a stray value, a positional, or an
# option that chooses the conversation (it would contest --resume) or never starts an interactive one.
function Assert-ExtraArgs([hashtable[]]$Groups) {
    foreach ($group in $Groups) {
        $token = $group.Tokens[0]
        if ($group.Positional) {
            throw "-ExtraArgs takes only options, but '$token' is not one or its value. Pass the first message with -Prompt; give an option the parser cannot place its value as --opt=value."
        }
        if ($group.Names.Where({ $_ -in $SessionSelectors })) { throw "-ExtraArgs cannot carry $token`: the restart itself chooses the conversation to resume." }
        if ($group.Names.Where({ $_ -in $ExtraArgRejects })) { throw "-ExtraArgs cannot carry $token`: it ends the launch or starts no interactive session." }
        if ($group.Kind -eq 'required' -and -not $group.Values) { throw "-ExtraArgs: $token needs a value." }
    }
}

# Base64 of a UTF-8 JSON string array, so the worker's command line needs no quoting of the
# strings' own quotes and backslashes.
function ConvertTo-WorkerArg([string[]]$Strings) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Strings -Compress)))
}

$agentPid = Get-AgentPid
$sessionId = Get-AgentSessionId
if (-not $agentPid -or -not $sessionId) { throw "No $AgentName process or session id in this shell's environment; run it from a $AgentName tool call." }

$agent = Get-CimInstance Win32_Process -Filter "ProcessId=$agentPid"
$shell = Get-CimInstance Win32_Process -Filter "ProcessId=$($agent.ParentProcessId)"
# The typed line uses PowerShell quoting, and only an interactive shell reads it back as a command.
if (-not $ExitOnly -and $shell.Name -notin 'pwsh.exe', 'powershell.exe') {
    throw "$AgentName was launched by $($shell.Name), not PowerShell; restarting would only exit it."
}

# The tool call is the process the agent spawned for it: this shell's ancestor whose parent is the agent.
$toolCall = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
while ($toolCall -and $toolCall.ParentProcessId -ne $agent.ProcessId) {
    $toolCall = Get-CimInstance Win32_Process -Filter "ProcessId=$($toolCall.ParentProcessId)"
}
if (-not $toolCall) { throw "This shell does not descend from $AgentName (PID $agentPid); run it from a $AgentName tool call." }

$workerArgs = @('-Sdk', $Sdk, '-AgentPid', $agentPid, '-SessionId', $sessionId, '-ToolCallPid', $toolCall.ProcessId)
if ($ExitOnly) { $workerArgs += '-ExitOnly' }
else {
    # Built here, while the agent runs: its command line is readable only then, and a rejected
    # -ExtraArgs must fail this call rather than leave the agent exited.
    $argv = [SessionConsole]::SplitCommandLine($agent.CommandLine)
    $exe = $argv[0]
    $table = Get-OptionTable $exe
    $extraGroups = @(Get-ArgGroups $ExtraArgs $table $exe)
    Assert-ExtraArgs $extraGroups
    $keptArgs = @(Get-KeptLaunchArgs ($argv | Select-Object -Skip 1) $table $exe)
    $resumeArgs = $keptArgs + @($ExtraArgs | Where-Object { $_ }) + '--resume', $sessionId
    Test-ResumeArgs $exe $resumeArgs
    $workerArgs += '-ResumeArgs', (ConvertTo-WorkerArg $resumeArgs)
    # Trust the agent would ask for at startup because of the relaunch args. Found and checked here
    # so a bad extra value fails this call; granted by the worker after the exit, so the exiting
    # agent cannot overwrite it with the state it holds in memory.
    $trust = @(Get-RelaunchTrust @(Get-ArgGroups $keptArgs $table $exe) $extraGroups)
    if ($trust) { $workerArgs += '-Trust', (ConvertTo-WorkerArg $trust) }
}
if ($DelaySeconds) { $workerArgs += '-DelaySeconds', $DelaySeconds.ToString([cultureinfo]::InvariantCulture) }
if ($Prompt) {
    # Kept in a file so the typed line stays short ASCII: newlines, quotes, and non-ASCII text in
    # the prompt cannot be typed as keystrokes reliably.
    $promptFile = Join-Path $env:TEMP "$Sdk-restart-$sessionId.prompt"
    Set-Content -LiteralPath $promptFile -Value $Prompt -NoNewline -Encoding utf8
    $workerArgs += '-PromptFile', $promptFile
}

$worker = Join-Path $PSScriptRoot 'restart-worker.ps1'
$commandLine = (@((Get-Command pwsh).Source, '-NoProfile', '-NonInteractive', '-File', $worker) + $workerArgs |
    ForEach-Object { '"' + "$_".Replace('"', '\"') + '"' }) -join ' '
[SessionConsole]::StartWithoutWindow($commandLine) | Out-Null
