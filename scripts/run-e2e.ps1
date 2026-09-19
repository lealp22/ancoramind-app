<#
.SYNOPSIS
    Starts the local AncoraMind Telegram E2E flow from PowerShell.

.DESCRIPTION
    The local flow validates .env without evaluating it as PowerShell, prepares a
    local PostgreSQL only when configured, obtains an ngrok HTTPS URL, registers
    the Telegram webhook and starts AncoraMind.

    Pass -PublicBaseUrl for an already deployed HTTPS service (for example
    Railway). In that mode the script validates configuration and registers the
    webhook against the remote service; it never starts ngrok, Docker or a local
    AncoraMind process.

.EXAMPLE
    .\scripts\run-e2e.ps1 -Check
    .\scripts\run-e2e.ps1
    .\scripts\run-e2e.ps1 -Reset
    .\scripts\run-e2e.ps1 -PublicBaseUrl https://ancoramind-app-production.up.railway.app
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Reset,
    [string]$PublicBaseUrl,
    [int]$Port = 7777,
    [string]$EnvFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDirectory = Split-Path -Parent $PSCommandPath
$ProjectRoot = Split-Path -Parent $ScriptDirectory
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $ProjectRoot ".env"
}

function Write-Info {
    param([string]$Message)
    Write-Host "[info] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[ ok ] $Message" -ForegroundColor Green
}

function Write-WarningMessage {
    param([string]$Message)
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Get-EnvironmentValue {
    param([string]$Name)
    return [Environment]::GetEnvironmentVariable($Name, "Process")
}

function Require-EnvironmentValue {
    param([string]$Name)
    $value = Get-EnvironmentValue $Name
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name is required in $EnvFile"
    }
    return $value
}

function Get-RequiredCommand {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "$Name not found. Install it first."
    }
    return $command
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ".env not found at $Path. Copy .env.example and fill in the required values."
    }

    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $lineNumber += 1
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $match = [regex]::Match(
            $line,
            '^\s*(?:export\s+)?(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)\s*$'
        )
        if (-not $match.Success) {
            throw "Invalid .env assignment at ${Path}:$lineNumber"
        }

        $key = $match.Groups["key"].Value
        $value = $match.Groups["value"].Value
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        # Deliberately set a literal process variable. Never Invoke-Expression,
        # dot-source, expand command substitutions, or execute .env contents.
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }

    Write-Ok "Loaded .env assignments without executing them"
}

function Test-PublicBaseUrl {
    param([string]$Value)

    try {
        $uri = [Uri]$Value
    }
    catch {
        throw "PublicBaseUrl must be a clean HTTPS URL"
    }
    if (
        -not $uri.IsAbsoluteUri -or
        $uri.Scheme -ne "https" -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or
        -not [string]::IsNullOrWhiteSpace($uri.Query) -or
        -not [string]::IsNullOrWhiteSpace($uri.Fragment) -or
        -not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or
        ($uri.AbsolutePath -ne "/" -and -not [string]::IsNullOrWhiteSpace($uri.AbsolutePath))
    ) {
        throw "PublicBaseUrl must be a clean HTTPS URL"
    }
    return $uri.GetLeftPart([System.UriPartial]::Authority).TrimEnd("/")
}

function Resolve-NgrokCommand {
    $command = Get-Command "ngrok" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $fallback = Join-Path $HOME "tools\ngrok.exe"
    if (Test-Path -LiteralPath $fallback -PathType Leaf) {
        return $fallback
    }
    throw "ngrok not found in PATH or at $fallback"
}

function Get-NgrokPublicUrl {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
        foreach ($tunnel in @($response.tunnels)) {
            if ($tunnel.public_url -is [string] -and $tunnel.public_url.StartsWith("https://")) {
                return $tunnel.public_url.TrimEnd("/")
            }
        }
    }
    catch {
        return $null
    }
    return $null
}

function Start-LocalPostgres {
    Set-Location $ProjectRoot
    $runningServices = @(& docker compose ps --status running --services 2>$null)
    if ($runningServices -contains "postgres") {
        Write-Ok "PostgreSQL already running"
    }
    else {
        Write-Info "Starting local PostgreSQL..."
        & docker compose up postgres -d
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start PostgreSQL"
        }
    }

    Write-Info "Waiting for PostgreSQL..."
    $ready = $false
    for ($attempt = 1; $attempt -le 30; $attempt += 1) {
        & docker compose exec -T postgres pg_isready -U ancora -d ancoramind *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        throw "PostgreSQL not ready after 30 seconds"
    }
    Write-Ok "PostgreSQL is ready"

    & docker compose exec -T postgres psql -U ancora -d ancoramind -c "SELECT 1 FROM ancora.notes LIMIT 1" *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Migrations already applied"
    }
    else {
        Write-Info "Applying local bootstrap migrations..."
        Get-Content -LiteralPath (Join-Path $ProjectRoot "migrations\init.sql") -Raw |
            & docker compose exec -T postgres psql -U ancora -d ancoramind
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to apply local bootstrap migrations"
        }
        Write-Ok "Migrations applied"
    }

    $tableCount = (
        & docker compose exec -T postgres psql -U ancora -d ancoramind -tAc `
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='ancora'" 2>$null |
            Out-String
    ).Trim()
    return "local PostgreSQL ($tableCount domain tables)"
}

function Register-TelegramWebhook {
    param(
        [string]$PythonPath,
        [string]$BaseUrl,
        [switch]$DeleteFirst
    )

    Set-Location $ProjectRoot
    if ($DeleteFirst) {
        Write-Info "Deleting the existing Telegram webhook..."
        & $PythonPath "scripts/telegram_webhook.py" delete
        if ($LASTEXITCODE -ne 0) {
            throw "Could not delete the existing Telegram webhook"
        }
    }

    Write-Info "Registering Telegram webhook..."
    & $PythonPath "scripts/telegram_webhook.py" set --base-url $BaseUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Could not register the Telegram webhook"
    }
    return "$BaseUrl/telegram/webhook"
}

function Test-E2EConfiguration {
    param([bool]$UsesPublicBaseUrl)

    $python = Get-RequiredCommand "python"
    $provider = Require-EnvironmentValue "LLM_PROVIDER"
    $telegramToken = Require-EnvironmentValue "TELEGRAM_TOKEN"
    $databaseUrl = Require-EnvironmentValue "ANCORA_DATABASE_URL"
    $storageBackend = (Get-EnvironmentValue "DOCUMENT_STORAGE_BACKEND")
    if ([string]::IsNullOrWhiteSpace($storageBackend)) {
        $storageBackend = "local"
    }
    $storageBackend = $storageBackend.Trim().ToLowerInvariant()

    switch ($provider.Trim().ToLowerInvariant()) {
        "openai" {
            if ([string]::IsNullOrWhiteSpace((Get-EnvironmentValue "OPENAI_API_KEY"))) {
                Write-WarningMessage "OPENAI_API_KEY is not set"
            }
        }
        "openrouter" {
            if ([string]::IsNullOrWhiteSpace((Get-EnvironmentValue "OPENROUTER_API_KEY"))) {
                Write-WarningMessage "OPENROUTER_API_KEY is not set"
            }
        }
        "openai-like" {
            Require-EnvironmentValue "LLM_BASE_URL" | Out-Null
            if ([string]::IsNullOrWhiteSpace((Get-EnvironmentValue "OPENAI_API_KEY"))) {
                Write-WarningMessage "OPENAI_API_KEY is not set"
            }
        }
        default {
            throw "Unknown LLM_PROVIDER: $provider (use: openai, openrouter, openai-like)"
        }
    }

    $litellmProxyEnabled = Get-EnvironmentValue "LITELLM_PROXY_ENABLED"
    if (
        -not [string]::IsNullOrWhiteSpace($litellmProxyEnabled) -and
        $litellmProxyEnabled.Trim().ToLowerInvariant() -eq "true"
    ) {
        Require-EnvironmentValue "LITELLM_PROXY_BASE_URL" | Out-Null
        Require-EnvironmentValue "LITELLM_PROXY_VIRTUAL_KEY" | Out-Null
    }

    switch ($storageBackend) {
        "local" { }
        "supabase" {
            $supabaseUrl = Require-EnvironmentValue "SUPABASE_URL"
            Require-EnvironmentValue "SUPABASE_SERVICE_ROLE_KEY" | Out-Null
            if ($supabaseUrl -like "*.storage.supabase.co*") {
                throw "SUPABASE_URL must be the project URL, not the storage host"
            }
        }
        default {
            throw "Unknown DOCUMENT_STORAGE_BACKEND: $storageBackend (use: local, supabase)"
        }
    }

    $usesLocalDatabase = $databaseUrl -match "(?i)(localhost|127\.0\.0\.1|\[::1\])"
    if ($usesLocalDatabase -and -not $UsesPublicBaseUrl) {
        Get-RequiredCommand "docker" | Out-Null
    }

    [PSCustomObject]@{
        PythonPath = $python.Source
        Provider = $provider.Trim().ToLowerInvariant()
        StorageBackend = $storageBackend
        UsesLocalDatabase = $usesLocalDatabase
        TelegramConfigured = -not [string]::IsNullOrWhiteSpace($telegramToken)
    }
}

try {
    Set-Location $ProjectRoot
    Import-DotEnv $EnvFile

    $normalizedPublicBaseUrl = $null
    if (-not [string]::IsNullOrWhiteSpace($PublicBaseUrl)) {
        $normalizedPublicBaseUrl = Test-PublicBaseUrl $PublicBaseUrl
    }

    $configuration = Test-E2EConfiguration ($null -ne $normalizedPublicBaseUrl)
    if ($null -eq $normalizedPublicBaseUrl) {
        $ngrokCommand = Resolve-NgrokCommand
    }

    $databaseMode = if ($configuration.UsesLocalDatabase) { "local" } else { "managed" }
    $endpointMode = if ($null -ne $normalizedPublicBaseUrl) { "public HTTPS" } else { "local ngrok" }
    Write-Ok (
        "Prerequisites OK - provider: {0} | database: {1} | storage: {2} | endpoint: {3}" -f
        $configuration.Provider, $databaseMode, $configuration.StorageBackend, $endpointMode
    )

    if ($Check) {
        Write-Info "Check-only mode. No Docker, ngrok, Telegram, or app actions were performed."
        exit 0
    }

    if ($null -ne $normalizedPublicBaseUrl) {
        $webhookUrl = Register-TelegramWebhook `
            -PythonPath $configuration.PythonPath `
            -BaseUrl $normalizedPublicBaseUrl `
            -DeleteFirst:$Reset
        Write-Ok "Remote webhook configured: $webhookUrl"
        Write-Info "PublicBaseUrl mode does not start Docker, ngrok, or a local AncoraMind process."
        exit 0
    }

    if ($configuration.UsesLocalDatabase) {
        $databaseLabel = Start-LocalPostgres
    }
    else {
        $databaseLabel = "managed PostgreSQL (Supabase/pooler)"
        Write-Info "Managed database detected - Docker and local migrations skipped"
    }

    $ngrokUrl = Get-NgrokPublicUrl
    if ([string]::IsNullOrWhiteSpace($ngrokUrl)) {
        Write-Info "Starting ngrok in the background..."
        Start-Process -FilePath $ngrokCommand -ArgumentList @("http", "$Port") -WindowStyle Hidden | Out-Null
        for ($attempt = 1; $attempt -le 30; $attempt += 1) {
            Start-Sleep -Seconds 1
            $ngrokUrl = Get-NgrokPublicUrl
            if (-not [string]::IsNullOrWhiteSpace($ngrokUrl)) {
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($ngrokUrl)) {
        throw "Failed to get an ngrok URL. Start manually: ngrok http $Port"
    }
    Write-Ok "ngrok endpoint: $ngrokUrl"

    $webhookUrl = Register-TelegramWebhook `
        -PythonPath $configuration.PythonPath `
        -BaseUrl $ngrokUrl `
        -DeleteFirst:$Reset

    Write-Host ""
    Write-Host "AncoraMind local E2E is ready" -ForegroundColor Green
    Write-Host "  Provider:  $($configuration.Provider)"
    $model = Get-EnvironmentValue "LLM_MODEL"
    if ([string]::IsNullOrWhiteSpace($model)) {
        $model = "gpt-5.6-luna"
    }
    Write-Host "  Model:     $model"
    Write-Host "  Webhook:   $webhookUrl"
    Write-Host "  Database:  $databaseLabel"
    Write-Host "  Storage:   $($configuration.StorageBackend)"
    Write-Host ""
    Write-Info "Starting AncoraMind (Ctrl+C to stop)..."
    & $configuration.PythonPath -m src.main
    exit $LASTEXITCODE
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}