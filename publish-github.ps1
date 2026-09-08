# Run explicitly from PowerShell after installing Git and GitHub CLI.
# This script creates a NEW PRIVATE repository only for the verified owner.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git first: https://git-scm.com/download/win' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI first: https://cli.github.com/' }
$login = gh api user --jq .login
if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login first, then rerun this script.' }
if ($login.Trim() -ne 'badbed7') { throw 'This project is for badbed7. Switch GitHub CLI to that account first.' }
$existing = gh repo list badbed7 --limit 1000 --json name --jq '.[].name'
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect repositories. No repository was changed.' }
if (@($existing) -contains 'morning-bloom') { throw 'badbed7/morning-bloom already exists. No repository was changed. Send its URL to Codex to continue.' }
if (-not (Test-Path .git)) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
}
$remotes = git remote
if (@($remotes) -contains 'origin') { throw 'This folder already has an origin. No remote was changed.' }
git config user.name badbed7
git config user.email '55682211+badbed7@users.noreply.github.com'
git add --all
if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
$staged = git diff --cached --name-only
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged files' }
if ($staged) {
    git commit -m 'feat: start Morning Bloom desktop prototype with approved game design'
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
}
gh repo create badbed7/morning-bloom --private --description 'Morning Bloom: a small desktop flower-growing game built with Godot' --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw 'GitHub create/push failed. Existing local work is preserved.' }
Write-Host 'Created and pushed: https://github.com/badbed7/morning-bloom'
