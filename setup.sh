#!/bin/bash
set -e

echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip unzip

echo "Unzipping deploy.zip using Python..."
python3 -c "import zipfile; zipfile.ZipFile('deploy.zip', 'r').extractall('/home/$USER/AlphaPulse')"
cd ~/AlphaPulse

echo "Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt
mkdir -p data logs

echo "Configuring crontab..."
crontab -l | grep -v 'AlphaPulse' > mycron || true
echo "0 22,9 * * * cd /home/\$USER/AlphaPulse && /home/\$USER/AlphaPulse/.venv/bin/python main.py run >> /home/\$USER/AlphaPulse/logs/cron.log 2>&1" >> mycron
crontab mycron
rm mycron

echo "Setup complete!"
