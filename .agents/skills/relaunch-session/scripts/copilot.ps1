# GitHub Copilot CLI specifics, dot-sourced by restart.ps1 and restart-worker.ps1.

$AgentName = 'Copilot CLI'
# The executable, not `copilot`: a shell function or alias named copilot may add arguments the
# process already received, so the relaunch would repeat them. PATH resolves it as a wrapper would.
$AgentCommand = 'copilot.exe'

# Each Ctrl+C takes one step: cancel the turn, clear the input, arm the exit confirmation, then
# quit. The requesting turn is usually still running when the presses start, so press until it exits.
$CtrlCPresses = 5
$CtrlCIntervalMs = 500

# Options that choose or seed the conversation; a restart replaces them with --resume <current session>.
# The hidden --worktree, --cloud, and --new-session-id start a new session and clap refuses them with --resume.
$SessionSelectors = '--resume', '--continue', '--session-id', '--connect', '--name',
    '--interactive', '--prompt', '--fleet', '--attachment', '--worktree', '--cloud', '--new-session-id'

# Options that end the launch or start no TUI; -ExtraArgs rejects them too.
$ExtraArgRejects = '--acp', '--help', '--version', '--server', '--headless', '--managed-server',
    '--stdio', '--embedded-host', '--print-debug-info', '--collect-debug-logs'

# clap validates conflicts and enum values before acting on --version, so this dry run rejects a
# relaunch that would fail (e.g. --mode over an original --autopilot) while the agent still runs.
function Test-ResumeArgs([string]$Exe, [string[]]$ResumeArgs) {
    $output = & $Exe @ResumeArgs --version 2>&1
    if ($LASTEXITCODE) { throw "copilot rejects the relaunch args: $output" }
}

# copilot asks at startup to trust its working directory unless that directory, an ancestor, or its
# git root is in `trustedFolders` of config.json, and its own message for an untrusted folder says
# to add the folder there. With --resume the working directory is the last -C, else the session's
# stored cwd. A "Yes" at the prompt holds only for that run, so the relaunch needs the entry too.
# The config directory is the last --config-dir, else COPILOT_HOME, else ~/.copilot.
function Get-CopilotHome([hashtable[]]$Groups) {
    $configDir = @($Groups.Where({ $_.Names -contains '--config-dir' }).ForEach({ $_.Values }))[-1]
    $configDir ?? $env:COPILOT_HOME ?? (Join-Path $HOME '.copilot')
}

# config.json starts with // comment lines, which JSON readers must be told to skip.
function ConvertFrom-CopilotConfig([string]$Text) {
    if (-not $Text) { return }
    $options = [System.Text.Json.JsonDocumentOptions]@{ CommentHandling = 'Skip'; AllowTrailingCommas = $true }
    # The comma keeps PowerShell from enumerating the returned object into its properties.
    , [System.Text.Json.Nodes.JsonNode]::Parse($Text, $null, $options)
}
function Get-TrustedFolders([string]$Text) {
    @((ConvertFrom-CopilotConfig $Text)?['trustedFolders']?.AsArray().ForEach({ $_.GetValue[string]() }))
}

function Test-FolderTrusted([string]$Dir, [string[]]$Trusted, [switch]$NoGitRoot) {
    $covering = @(for ($d = $Dir; $d; $d = Split-Path -Parent $d) { $d.TrimEnd('\') })
    $root = if (-not $NoGitRoot -and (Get-Command git -ErrorAction Ignore)) { git -C $Dir rev-parse --show-toplevel 2>$null }
    if ($LASTEXITCODE -eq 0 -and $root) { $covering += [IO.Path]::GetFullPath($root).TrimEnd('\') }
    # -contains compares case-insensitively, as Windows paths do.
    [bool]$Trusted.Where({ $covering -contains $_.TrimEnd('\') })
}

# Returns the config.json path, then each directory to add to its trustedFolders; nothing when the
# working directory is already trusted. A relative -C resolves against the launching shell's
# directory, which this tool shell cannot see: an extra one is refused, a kept one is left to ask.
function Get-RelaunchTrust([hashtable[]]$KeptGroups, [hashtable[]]$ExtraGroups) {
    foreach ($dir in $ExtraGroups.Where({ $_.Names -contains '-C' }).ForEach({ $_.Values })) {
        if (-not [IO.Path]::IsPathFullyQualified($dir)) { throw "-ExtraArgs: give -C an absolute path, not '$dir'." }
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw "-ExtraArgs: -C '$dir' is not an existing directory." }
    }
    $groups = @($KeptGroups) + @($ExtraGroups)
    $copilotHome = Get-CopilotHome $groups
    $dir = @($groups.Where({ $_.Names -contains '-C' }).ForEach({ $_.Values }))[-1]
    if (-not $dir) {
        $workspace = Join-Path $copilotHome "session-state\$(Get-AgentSessionId)\workspace.yaml"
        $dir = (Get-Content -LiteralPath $workspace -ErrorAction Ignore) -match '^cwd: ' -replace '^cwd: ', '' | Select-Object -First 1
    }
    if (-not $dir -or -not [IO.Path]::IsPathFullyQualified($dir) -or -not (Test-Path -LiteralPath $dir -PathType Container)) { return }
    $dir = [IO.Path]::GetFullPath($dir)
    if ($dir.Length -gt 3) { $dir = $dir.TrimEnd('\') }
    $configPath = Join-Path $copilotHome 'config.json'
    $trusted = Get-TrustedFolders (Get-Content -Raw -LiteralPath $configPath -ErrorAction Ignore)
    if (-not (Test-FolderTrusted $dir $trusted)) { $configPath, $dir }
}

# Runs after copilot has exited, under its trusted-folders lock and every other config.json lock
# present, so no copilot writes config.json meanwhile. The entry is inserted into the text rather
# than the file re-serialized, which keeps the comments and every other byte. Writes nothing to the host.
function Grant-ExtraArgTrust([string[]]$Items) {
    $configPath, $dirs = $Items
    # Listed from the directory so each lock appears once, under one spelling of its path.
    [IO.File]::Open("$configPath.trusted-folders.lock", 'OpenOrCreate', 'ReadWrite', 'ReadWrite, Delete').Dispose()
    $lockPaths = (Get-ChildItem -LiteralPath (Split-Path $configPath) -Filter 'config.json.*.lock').FullName | Sort-Object
    $locks = [System.Collections.Generic.List[IO.FileStream]]::new()
    try {
        foreach ($lockPath in $lockPaths) {
            $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'ReadWrite, Delete')
            $locks.Add($lock)
            $deadline = (Get-Date).AddSeconds(10)
            while ($true) {
                try { $lock.Lock(0, 1); break }
                catch [IO.IOException] { if ((Get-Date) -gt $deadline) { throw "$lockPath stayed locked." }; Start-Sleep -Milliseconds 100 }
            }
        }
        $original = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { "{}`n" }
        $text = $original
        # Checked again under the lock, since another copilot may have added a covering folder since;
        # by the folder and its ancestors only, as no native command can start on the exited agent's console.
        foreach ($dir in $dirs) { if (-not (Test-FolderTrusted $dir (Get-TrustedFolders $text) -NoGitRoot)) { $text = Add-TrustedFolderText $text $dir } }
        if ($text -eq $original) { return }
        # The result must still parse and must differ from the original only in trustedFolders.
        $before, $after = (ConvertFrom-CopilotConfig $original), (ConvertFrom-CopilotConfig $text)
        foreach ($node in $before, $after) { [void]$node.AsObject().Remove('trustedFolders') }
        if ($before.ToJsonString() -ne $after.ToJsonString()) { throw 'Inserting into trustedFolders would change other settings.' }
        $temp = "$configPath.$PID.tmp"
        [IO.File]::WriteAllText($temp, $text, [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temp, $configPath, $true)
    }
    finally {
        foreach ($lock in $locks) { $lock.Dispose() }
    }
}

# Appends one JSON string to the trustedFolders array, creating the key at the top of the root
# object when it is missing, and leaves all other text as it was.
function Add-TrustedFolderText([string]$Text, [string]$Dir) {
    $entry = [System.Text.Json.JsonSerializer]::Serialize($Dir, [System.Text.Json.JsonSerializerOptions]@{
        Encoder = [System.Text.Encodings.Web.JavaScriptEncoder]::UnsafeRelaxedJsonEscaping })
    $key = [regex]::Match($Text, '"trustedFolders"\s*:\s*\[')
    if (-not $key.Success) {
        $root = [regex]::Match($Text, '(?m)^\{')
        if (-not $root.Success) { throw 'config.json has no root object to add trustedFolders to.' }
        return $Text.Insert($root.Index + 1, "`n  `"trustedFolders`": [`n    $entry`n  ],")
    }
    # The closing bracket is the first ']' outside a string; paths may contain ']' themselves.
    $inString = $false
    for ($i = $key.Index + $key.Length; $i -lt $Text.Length; $i++) {
        $char = $Text[$i]
        if ($inString) { if ($char -eq '\') { $i++ } elseif ($char -eq '"') { $inString = $false } }
        elseif ($char -eq '"') { $inString = $true }
        elseif ($char -eq ']') { break }
    }
    $body = $Text.Substring($key.Index + $key.Length, $i - $key.Index - $key.Length)
    if (-not $body.Trim()) { return $Text.Insert($key.Index + $key.Length, "`n    $entry`n  ") }
    $last = $key.Index + $key.Length + $body.TrimEnd().Length
    $indent = if ($body -match '^\s*?\n([ \t]*)') { $Matches[1] } else { ' ' }
    $Text.Insert($last, ",`n$indent$entry")
}

# COPILOT_LOADER_PID is inherited by a copilot started from another copilot's shell, so it can
# name the outer one; the nearest copilot ancestor of this shell is the agent that owns it.
function Get-AgentPid {
    $exe = if ($env:COPILOT_CLI_PATH) { Split-Path -Leaf $env:COPILOT_CLI_PATH } else { 'copilot.exe' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
    while ($process -and $process.Name -ne $exe) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
    }
    if ($process) { [uint32]$process.ProcessId }
}
function Get-AgentSessionId { $env:COPILOT_AGENT_SESSION_ID }

# Maps every option spelling to its canonical name and value arity, read from clap's
# `copilot --help` so the table follows the installed version. Canonical is the long name, or
# the short one for short-only options such as `-C <directory>`. `--opt[=<v>]` also takes its
# value as the next word (`--sync-session off`), so it is optional.
function Get-OptionTable([string]$Exe) {
    $table = [hashtable]::new([StringComparer]::Ordinal)
    $pattern = '^ {2}(?:(?<short>-\w)(?:, )?)? *(?<long>--[\w-]+)?(?<inline>\[=.*)?(?<value> \[?<[^>]*>(?<many>\.\.\.)?\]?)?$'
    foreach ($line in & $Exe --help) {
        if ($line -notmatch $pattern -or -not ($Matches.short -or $Matches.long)) { continue }
        $kind = if ($Matches.inline) { 'optional' }
            elseif (-not $Matches.value) { 'none' }
            elseif ($Matches.many) { 'variadic' }
            elseif ($Matches.value.StartsWith(' [')) { 'optional' }
            else { 'required' }
        $option = @{ Name = if ($Matches.long) { $Matches.long } else { $Matches.short }; Kind = $kind }
        foreach ($spelling in $Matches.short, $Matches.long) { if ($spelling) { $table[$spelling] = $option } }
    }
    # --help omits hidden options. These spellings must resolve to their canonical names for the
    # selector checks: -w is --worktree and --effort is --reasoning-effort in clap's own errors.
    $worktree = @{ Name = '--worktree'; Kind = 'optional' }
    foreach ($spelling in '-w', '--worktree') { if (-not $table[$spelling]) { $table[$spelling] = $worktree } }
    if (-not $table['--effort'] -and $table['--reasoning-effort']) { $table['--effort'] = $table['--reasoning-effort'] }
    return $table
}

# A copilot that started interactively had no subcommand, and clap rejects option values that
# start with '-', so every word after an option missing from the table belongs to it.
$UnknownOptionKind = 'variadic'
function Resolve-Option([hashtable]$Table, [string]$Spelling, [string]$Exe) { $Table[$Spelling] }

# copilot's positionals are subcommands; an interactive session's initial prompt is -i.
function Format-PromptArg([string]$Expression) { " -i $Expression" }
