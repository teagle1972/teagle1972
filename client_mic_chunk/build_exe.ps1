param(
    [string]$PythonExe = "d:\anaconda3\envs\aliyun\python.exe"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$uiSpec = Join-Path $root "client_mic_chunk_ui_v1.spec"
$backendSpec = Join-Path $root "mic_chunk_client_backend.spec"

if (!(Test-Path $PythonExe)) {
    throw "Python not found: $PythonExe"
}

Push-Location $root
try {
    & $PythonExe -m PyInstaller --noconfirm --clean $uiSpec
    & $PythonExe -m PyInstaller --noconfirm --clean $backendSpec

    $distRoot = Join-Path $root "dist\\client_mic_chunk_ui_v1"
    $internalDir = Join-Path $root "dist\\client_mic_chunk_ui_v1\\_internal"
    $backendDirSrc = Join-Path $root "dist\\mic_chunk_client_backend"
    $backendDirDst = Join-Path $distRoot "backend_runtime"
    $tclDll = Join-Path (Split-Path $PythonExe -Parent) "Library\\bin\\tcl86t.dll"
    $tkDll = Join-Path (Split-Path $PythonExe -Parent) "Library\\bin\\tk86t.dll"
    $templateWorkflowSrc = Join-Path $root "Data\\_template\\_ui_tab_workflow.json"
    $templateWorkflowDstDir = Join-Path $distRoot "Data\\_template"

    if (!(Test-Path $internalDir)) {
        throw "PyInstaller output not found: $internalDir"
    }
    if (Test-Path $tclDll) {
        Copy-Item $tclDll (Join-Path $internalDir "tcl86t.dll") -Force
    }
    if (Test-Path $tkDll) {
        Copy-Item $tkDll (Join-Path $internalDir "tk86t.dll") -Force
    }
    if (Test-Path $templateWorkflowSrc) {
        New-Item -ItemType Directory -Path $templateWorkflowDstDir -Force | Out-Null
        Copy-Item $templateWorkflowSrc (Join-Path $templateWorkflowDstDir "_ui_tab_workflow.json") -Force
    }
    if (Test-Path $backendDirSrc) {
        if (Test-Path $backendDirDst) {
            Remove-Item $backendDirDst -Recurse -Force
        }
        Copy-Item $backendDirSrc $backendDirDst -Recurse -Force
    }
}
finally {
    Pop-Location
}
