cd C:\Users\Julio\Desktop\print-collect\server
python _teste_final_sem_requests.py 2>&1 | Out-File -FilePath C:\Users\Julio\Desktop\print-collect\server\_teste_saida_ps1.txt -Encoding utf8
Write-Host "DONE, RC=$LASTEXITCODE"
