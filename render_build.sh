#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

echo "Starting custom build process"

# Set up Chrome
STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "Downloading Chrome"
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  
  # Install Chrome dependencies
  sudo apt-get update
  sudo apt-get install -y ./google-chrome-stable_current_amd64.deb
  
  dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm ./google-chrome-stable_current_amd64.deb
  echo "Chrome downloaded and extracted"
else
  echo "Using Chrome from cache"
fi

# Install ChromeDriver
CHROME_VERSION=$(${STORAGE_DIR}/chrome/opt/google/chrome/chrome --version | cut -d ' ' -f 3)
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}")
wget -q -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip /tmp/chromedriver.zip -d ${STORAGE_DIR}/chrome/opt/google/chrome/
chmod +x ${STORAGE_DIR}/chrome/opt/google/chrome/chromedriver

# Print current directory and list contents
echo "Current directory: $(pwd)"
ls -la

# Try to find the project directory
if [ -d "/opt/render/project/src" ]; then
  echo "Found project directory at /opt/render/project/src"
  cd /opt/render/project/src
elif [ -d "$HOME/project" ]; then
  echo "Found project directory at $HOME/project"
  cd $HOME/project
else
  echo "Could not find project directory"
  exit 1
fi

# Print current directory and list contents again
echo "Current directory after cd: $(pwd)"
ls -la

# Install Python dependencies
echo "Installing Python dependencies"
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "requirements.txt not found"
  exit 1
fi

echo "Build process completed"
