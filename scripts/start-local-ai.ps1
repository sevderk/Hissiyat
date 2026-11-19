param(
    [string]$ModelDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Hissiyat\local-ai\qwen3-1.7b'),
    [ValidateRange(1024, 65535)][int]$Port = 8091
)

$ErrorActionPreference = 'Stop'
$modelFile = Join-Path $ModelDirectory 'Qwen3-1.7B-Q8_0.gguf'
$runtimeArchive = Join-Path $ModelDirectory 'llama-b12359-bin-win-cpu-x64.zip'
$runtimeExecutable = Join-Path $ModelDirectory 'runtime\llama-server.exe'
if (-not (Test-Path -LiteralPath $runtimeExecutable -PathType Leaf)) {
    throw 'The separately approved portable local runtime is missing.'
}
if ((Get-FileHash -LiteralPath $modelFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        '061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a' -or
    (Get-FileHash -LiteralPath $runtimeArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        '837c1655e87df3b66989f4be33a792a1399c785bf259038dc75c900096683e69') {
    throw 'Local model or runtime archive integrity check failed.'
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw 'The selected port is already in use. Keep the existing approved model session or select another port.'
}
Write-Output "Starting the local research model on 127.0.0.1:$Port. Use Ctrl+C to close it."
& $runtimeExecutable --model $modelFile --host 127.0.0.1 --port $Port --alias hissiyat-qwen3-1.7b `
    --ctx-size 8192 --parallel 1 --threads 4 --threads-batch 4 --n-gpu-layers 0 --offline `
    --log-disable --no-webui --no-context-shift --timeout 160 --no-jinja --chat-template chatml --reasoning off
exit $LASTEXITCODE
