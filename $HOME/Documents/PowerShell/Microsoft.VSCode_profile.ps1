# Initialize Conda
if (Test-Path "C:\Users\$env:USERNAME\anaconda3\Scripts\conda.exe") {
    (& "C:\Users\$env:USERNAME\anaconda3\Scripts\conda.exe" "shell.powershell" "hook") | Out-String | Invoke-Expression
} elseif (Test-Path "C:\ProgramData\anaconda3\Scripts\conda.exe") {
    (& "C:\ProgramData\anaconda3\Scripts\conda.exe" "shell.powershell" "hook") | Out-String | Invoke-Expression
}

# Initialize Conda for PowerShell
$condaPath = "$env:USERPROFILE\anaconda3"  # Adjust this path if your Anaconda is installed elsewhere
if (Test-Path $condaPath) {
    (& "$condaPath\Scripts\conda.exe" "shell.powershell" "hook") | Out-String | Invoke-Expression
}