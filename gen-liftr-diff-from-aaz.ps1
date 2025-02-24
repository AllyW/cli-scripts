
# $modules = @("astronomer", "liftrbasic", "arize-ai", "lambda-test", "mongo-db", "neon/postgres", "liftr-pilot", "pinecone", "qumulo", "weights-and-biases")
$modules = @("astronomer")

$scripts = "./aaz-dev/diff-aaz-model-from-swagger-tsp.py"

$swagger_aaz_base = "C:\Users\liwang3\workspace_tsp\swagger-res\aaz\Commands\"
$tsp_aaz_base = "C:\Users\liwang3\workspace_tsp\tsp-res\aaz\Commands\"

foreach ($moddir in $modules) {
    $swagger_aaz_dir = Join-Path -Path $swagger_aaz_base -ChildPath $moddir
    $tsp_aaz_dir = Join-Path -Path $tsp_aaz_base -ChildPath $moddir
    Write-Host "swagger aaz folder: $swagger_aaz_dir"
    Write-Host "tsp aaz folder: $tsp_aaz_dir"

    if ((Test-Path -Path $swagger_aaz_dir) -and (Test-Path -Path $tsp_aaz_dir)) {

        $command = "python $scripts --rpas $swagger_aaz_dir --rpat $tsp_aaz_dir"
        Write-Host "Run: $command"

        $process = Start-Process -FilePath "powershell.exe" -ArgumentList "-Command $command" -PassThru -Wait
#         $process = Invoke-Expression -Command $command
        if ($process.ExitCode -ne 0) {
            Write-Host "$moddir gen aaz model diff failed, pass"
            continue
        }
        else {
            Write-Host "$moddir gen aaz model diff succeed"
        }
    }
    else {
        Write-Host "$moddir under aaz base is not a directory, please check"
    }
}
