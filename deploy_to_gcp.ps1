$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine")+";"+[System.Environment]::GetEnvironmentVariable("PATH","User")+";C:\Users\0506h\AppData\Local\Google\google-cloud-sdk\bin"

Write-Host "Creating patch.tar..."
tar -cf patch.tar alphapulse/ main.py

Write-Host "Uploading to GCP VM..."
Write-Host "y" | gcloud.cmd compute scp patch.tar alphapulse:patch.tar --zone=us-west1-b

Write-Host "Extracting and Setting up crontab..."
$crontabCmd = "cd ~/AlphaPulse && tar -xf ../patch.tar && echo 'SHELL=/bin/bash' > mycron && echo '0 7,18 * * 1-6 cd ~/AlphaPulse && /home/0506h/AlphaPulse/.venv/bin/python main.py run >> /home/0506h/AlphaPulse/logs/cron_daily.log 2>&1' >> mycron && echo '0 11 * * 0 cd ~/AlphaPulse && /home/0506h/AlphaPulse/.venv/bin/python main.py run --weekly >> /home/0506h/AlphaPulse/logs/cron_weekly.log 2>&1' >> mycron && crontab mycron && rm mycron && crontab -l && echo '=== DEPLOY COMPLETE ==='"

Write-Host "y" | gcloud.cmd compute ssh alphapulse --zone=us-west1-b --command=$crontabCmd

Write-Host "Deployment completed!"
