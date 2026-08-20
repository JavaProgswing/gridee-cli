param(
    [string]$AndroidSdk = (Join-Path $env:LOCALAPPDATA 'Android\Sdk'),
    [string]$BuildToolsVersion = '35.0.0',
    [string]$JavaHome = $env:JAVA_HOME
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Join-Path $PSScriptRoot 'android-helper'
$BuildRoot = Join-Path $ProjectRoot 'build'
$ResolvedProject = [IO.Path]::GetFullPath($ProjectRoot)
$ResolvedBuild = [IO.Path]::GetFullPath($BuildRoot)
if (-not $ResolvedBuild.StartsWith($ResolvedProject + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean unexpected build path: $ResolvedBuild"
}
if (Test-Path -LiteralPath $ResolvedBuild) {
    Remove-Item -LiteralPath $ResolvedBuild -Recurse -Force
}

$Compiled = Join-Path $BuildRoot 'compiled.zip'
$Generated = Join-Path $BuildRoot 'generated'
$Classes = Join-Path $BuildRoot 'classes'
$Dex = Join-Path $BuildRoot 'dex'
$Unsigned = Join-Path $BuildRoot 'unsigned.apk'
$WithDex = Join-Path $BuildRoot 'with-dex.apk'
$Aligned = Join-Path $BuildRoot 'aligned.apk'
$Output = Join-Path $BuildRoot 'gridee-scheduler-debug.apk'
New-Item -ItemType Directory -Force -Path $BuildRoot,$Generated,$Classes,$Dex | Out-Null

$Tools = Join-Path $AndroidSdk "build-tools\$BuildToolsVersion"
$Aapt2 = Join-Path $Tools 'aapt2.exe'
$D8 = Join-Path $Tools 'd8.bat'
$ZipAlign = Join-Path $Tools 'zipalign.exe'
$ApkSigner = Join-Path $Tools 'apksigner.bat'
$AndroidJar = Join-Path $AndroidSdk 'platforms\android-35\android.jar'

$JavaHomes = @()
if ($JavaHome) { $JavaHomes += $JavaHome }
$JavacCommand = Get-Command javac -ErrorAction SilentlyContinue
if ($JavacCommand) { $JavaHomes += (Split-Path -Parent $JavacCommand.Source) | Split-Path -Parent }
$AndroidStudioJdk = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
if (Test-Path -LiteralPath $AndroidStudioJdk) { $JavaHomes += $AndroidStudioJdk }
$JavaRoot = Join-Path $env:ProgramFiles 'Java'
if (Test-Path -LiteralPath $JavaRoot) {
    $JavaHomes += Get-ChildItem -LiteralPath $JavaRoot -Directory |
        Sort-Object Name -Descending |
        ForEach-Object FullName
}
$JavaBin = $JavaHomes |
    Select-Object -Unique |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ 'bin\javac.exe')) -and
        (Test-Path -LiteralPath (Join-Path $_ 'bin\jar.exe'))
    } |
    Select-Object -First 1
if (-not $JavaBin) { throw 'Could not find a JDK containing javac.exe and jar.exe; pass -JavaHome.' }
$Javac = Join-Path $JavaBin 'bin\javac.exe'
$JarTool = Join-Path $JavaBin 'bin\jar.exe'
$DebugKey = Join-Path $env:USERPROFILE '.android\debug.keystore'
foreach ($Required in $Aapt2,$D8,$ZipAlign,$ApkSigner,$AndroidJar,$DebugKey) {
    if (-not (Test-Path -LiteralPath $Required)) { throw "Missing build dependency: $Required" }
}

& $Aapt2 compile --dir (Join-Path $ProjectRoot 'res') -o $Compiled
if ($LASTEXITCODE) { throw "aapt2 compile failed ($LASTEXITCODE)" }
& $Aapt2 link -I $AndroidJar --manifest (Join-Path $ProjectRoot 'AndroidManifest.xml') `
    --min-sdk-version 26 --target-sdk-version 35 --version-code 1 --version-name '1.0' `
    --java $Generated -o $Unsigned $Compiled
if ($LASTEXITCODE) { throw "aapt2 link failed ($LASTEXITCODE)" }

$JavaSources = @(
    Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'java') -Filter '*.java' -Recurse | ForEach-Object FullName
    Get-ChildItem -LiteralPath $Generated -Filter '*.java' -Recurse | ForEach-Object FullName
)
& $Javac -encoding UTF-8 -source 8 -target 8 -classpath $AndroidJar -d $Classes $JavaSources
if ($LASTEXITCODE) { throw "javac failed ($LASTEXITCODE)" }

$ClassFiles = @(Get-ChildItem -LiteralPath $Classes -Filter '*.class' -Recurse | ForEach-Object FullName)
& $D8 --lib $AndroidJar --min-api 26 --output $Dex $ClassFiles
if ($LASTEXITCODE) { throw "d8 failed ($LASTEXITCODE)" }

Copy-Item -LiteralPath $Unsigned -Destination $WithDex
Push-Location $Dex
try {
    & $JarTool uf $WithDex 'classes.dex'
    if ($LASTEXITCODE) { throw "jar update failed ($LASTEXITCODE)" }
} finally {
    Pop-Location
}
& $ZipAlign -f 4 $WithDex $Aligned
if ($LASTEXITCODE) { throw "zipalign failed ($LASTEXITCODE)" }
& $ApkSigner sign --ks $DebugKey --ks-key-alias androiddebugkey --ks-pass pass:android `
    --key-pass pass:android --out $Output $Aligned
if ($LASTEXITCODE) { throw "apksigner failed ($LASTEXITCODE)" }
& $ApkSigner verify --verbose $Output
if ($LASTEXITCODE) { throw "APK verification failed ($LASTEXITCODE)" }
Write-Host "Built $Output"

