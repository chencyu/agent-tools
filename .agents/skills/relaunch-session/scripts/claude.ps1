# Claude Code specifics, dot-sourced by restart.ps1 and restart-worker.ps1.

$AgentName = 'Claude Code'
$AgentCommand = 'claude'

# Claude Code treats the first Ctrl+C as cancelling the turn and the second as exit.
$CtrlCPresses = 2
$CtrlCIntervalMs = 300

# Options that choose or seed the conversation; a restart replaces them with --resume <current session>.
# --remote and --prefill are hidden from --help.
$SessionSelectors = '--resume', '--continue', '--session-id', '--fork-session', '--from-pr', '--teleport', '--cloud',
    '--remote', '--prefill'

# Options that end the launch without an interactive session; -ExtraArgs rejects them too.
$ExtraArgRejects = '--help', '--version', '--print', '--init-only'

# A word after an option claude does not define is its positional prompt.
$UnknownOptionKind = 'none'

# commander prints --version before validating any other option, so no dry run can check the
# relaunch args ahead of the exit; claude itself reports any error once relaunched.
function Test-ResumeArgs([string]$Exe, [string[]]$ResumeArgs) {}

# claude asks before --add-dir opens a directory no accepted workspace trust covers. Trust lives
# in ~/.claude.json as projects[<key>].hasTrustDialogAccepted, keyed on the git repository root
# (a worktree's main checkout), or outside a repository on the directory itself, which then
# covers its subdirectories; a repository nested in a trusted directory is not covered.
$ClaudeConfig = Join-Path ($env:CLAUDE_CONFIG_DIR ?? $HOME) '.claude.json'

function Get-TrustKey([string]$Dir) {
    $commonDir = if (Get-Command git -ErrorAction Ignore) { git -C $Dir rev-parse --path-format=absolute --git-common-dir 2>$null }
    $inRepo = $LASTEXITCODE -eq 0 -and $commonDir
    $root = if ($inRepo) { Split-Path $commonDir -Parent } else { [IO.Path]::GetFullPath($Dir).TrimEnd('\') }
    @{ Key = $root.Replace('\', '/'); InRepo = [bool]$inRepo }
}

function Get-AddDirs([hashtable[]]$Groups) { $Groups.Where({ $_.Names -contains '--add-dir' }).ForEach({ $_.Values }) }

# The trust keys the relaunch's --add-dir values need and lack. An answer at the dialog holds only
# for that run, so kept directories need trust as much as extra ones. A relative path resolves
# against the launching shell's directory, which this tool shell cannot see: an extra one is
# refused, a kept one is left to ask, as it did before.
function Get-RelaunchTrust([hashtable[]]$KeptGroups, [hashtable[]]$ExtraGroups) {
    foreach ($dir in Get-AddDirs $ExtraGroups) {
        if (-not [IO.Path]::IsPathFullyQualified($dir)) { throw "-ExtraArgs: give --add-dir an absolute path, not '$dir'." }
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw "-ExtraArgs: --add-dir '$dir' is not a directory." }
    }
    $projects = (Get-Content -Raw -LiteralPath $ClaudeConfig -ErrorAction Ignore | ConvertFrom-Json -AsHashtable)?.projects ?? @{}
    $trusted = @($projects.Keys.Where({ $projects[$_].hasTrustDialogAccepted }))
    $dirs = @(Get-AddDirs $KeptGroups) + @(Get-AddDirs $ExtraGroups)
    $keys = foreach ($dir in $dirs) {
        if (-not [IO.Path]::IsPathFullyQualified($dir) -or -not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
        $target = Get-TrustKey $dir
        $covered = $trusted.Where({ $_ -ieq $target.Key -or (-not $target.InRepo -and $target.Key.StartsWith("$_/", 'OrdinalIgnoreCase')) })
        if (-not $covered) { $target.Key }
    }
    $keys | Select-Object -Unique
}

# Runs after the exit, where no native command can start; every git lookup is done before it, by
# Get-RelaunchTrust. Edited as JSON nodes, which leave every other value as written (ConvertFrom-Json would turn
# date-like strings into dates), and replaced through a temporary file so no reader sees it half written.
function Grant-ExtraArgTrust([string[]]$Keys) {
    $config = [System.Text.Json.Nodes.JsonNode]::Parse((Get-Content -Raw -LiteralPath $ClaudeConfig))
    if ($null -eq $config['projects']) { $config['projects'] = [System.Text.Json.Nodes.JsonObject]::new() }
    foreach ($key in $Keys) {
        if ($null -eq $config['projects'][$key]) { $config['projects'][$key] = [System.Text.Json.Nodes.JsonObject]::new() }
        $config['projects'][$key]['hasTrustDialogAccepted'] = [System.Text.Json.Nodes.JsonValue]::Create($true)
    }
    $options = [System.Text.Json.JsonSerializerOptions]@{ WriteIndented = $true; Encoder = [System.Text.Encodings.Web.JavaScriptEncoder]::UnsafeRelaxedJsonEscaping }
    $temp = "$ClaudeConfig.relaunch-$PID"
    Set-Content -LiteralPath $temp -Value $config.ToJsonString($options) -Encoding utf8NoBOM -NoNewline
    Move-Item -LiteralPath $temp -Destination $ClaudeConfig -Force
}

function Get-AgentPid { [uint32]$env:CLAUDE_PID }
function Get-AgentSessionId { $env:CLAUDE_CODE_SESSION_ID }

# Maps every option spelling to its canonical name and value arity. Read from `claude --help`
# so the table follows the installed version.
function Get-OptionTable([string]$Exe) {
    $table = [hashtable]::new([StringComparer]::Ordinal)
    foreach ($line in & $Exe --help) {
        if ($line -notmatch '^  (?:(-\w), )?(--[\w-]+)(?:, (--[\w-]+))?(?: ([<\[])[^>\]]*?(\.\.\.)?[>\]])?') { continue }
        $kind = if ($Matches[5]) { 'variadic' } elseif ($Matches[4] -eq '<') { 'required' } elseif ($Matches[4]) { 'optional' } else { 'none' }
        $option = @{ Name = $Matches[2]; Kind = $kind }
        foreach ($spelling in $Matches[1], $Matches[2], $Matches[3]) { if ($spelling) { $table[$spelling] = $option } }
    }
    return $table
}

# A spelling `--help` lacks is looked up in the claude executable, which holds every option's
# commander definition literal, hidden ones included ("--agent-id <id>"). The same spelling can be
# defined by several subcommands, so it takes a value if any definition gives one. Reading the
# executable costs seconds, so it happens only on a miss; the answer, $null included, is cached.
function Resolve-Option([hashtable]$Table, [string]$Spelling, [string]$Exe) {
    if ($Table.ContainsKey($Spelling)) { return $Table[$Spelling] }
    $script:ExeText ??= [Text.Encoding]::Latin1.GetString([IO.File]::ReadAllBytes((Get-Command $Exe).Source))
    $definition = '"(?<flags>(?:--?[\w-]+, )*' + [regex]::Escape($Spelling) + '(?:, --?[\w-]+)*)(?: (?<open>[<\[])[^>\]"]*?(?<many>\.\.\.)?[>\]])?"'
    # A bare "--x" literal is any string, not evidence of a definition; a flag found only that way
    # stays unknown, which binds no value just as a flag does.
    $found = [regex]::Matches($script:ExeText, $definition).Where({ $_.Groups['open'].Success -or $_.Groups['flags'].Value.Contains(', ') })
    $option = if ($found.Count) {
        $withValue = $found.Where({ $_.Groups['open'].Success }, 'First') | Select-Object -First 1
        $kind = if (-not $withValue) { 'none' } elseif ($withValue.Groups['many'].Success) { 'variadic' } elseif ($withValue.Groups['open'].Value -eq '<') { 'required' } else { 'optional' }
        $long = ($found[0].Groups['flags'].Value -split ', ').Where({ $_.StartsWith('--') }, 'First')[0]
        @{ Name = $long ?? $Spelling; Kind = $kind }
    }
    $Table[$Spelling] = $option
    return $option
}

# The initial prompt is claude's positional argument.
function Format-PromptArg([string]$Expression) { " $Expression" }
