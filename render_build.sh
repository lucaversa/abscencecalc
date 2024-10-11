#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

echo "Starting custom build process"

# Install system dependencies
apt-get update && apt-get install -y wget

# Set up Chrome
STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "Downloading Chrome"
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm ./google-chrome-stable_current_amd64.deb
  echo "Chrome downloaded and extracted"
else
  echo "Using Chrome from cache"
fi

# Return to project directory
cd $RENDER_PROJECT_DIR

# Install Python dependencies
echo "Installing Python dependencies"
pip install -r requirements.txt

echo "Build process completed"
