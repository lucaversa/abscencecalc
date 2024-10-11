#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

echo "Starting custom build process"

# Set up Chrome
STORAGE_DIR=/opt/render/project/.render
CHROME_DIR=$STORAGE_DIR/chrome
CHROME_BIN=$CHROME_DIR/opt/google/chrome/chrome

echo "Storage directory: $STORAGE_DIR"
echo "Chrome directory: $CHROME_DIR"
echo "Chrome binary path: $CHROME_BIN"

if [[ ! -f $CHROME_BIN ]]; then
  echo "Chrome not found. Downloading and extracting..."
  mkdir -p $CHROME_DIR
  cd $CHROME_DIR
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  
  # Extract Chrome without installing
  dpkg -x ./google-chrome-stable_current_amd64.deb $CHROME_DIR
  rm ./google-chrome-stable_current_amd64.deb
  
  # Verify Chrome extraction
  if [[ -f $CHROME_BIN ]]; then
    echo "Chrome successfully extracted"
  else
    echo "Failed to extract Chrome"
    exit 1
  fi
else
  echo "Chrome already exists at $CHROME_BIN"
fi

# List Chrome directory contents
echo "Chrome directory contents:"
ls -R $CHROME_DIR

# Check Chrome version
if [[ -f $CHROME_BIN ]]; then
  CHROME_VERSION=$($CHROME_BIN --version)
  echo "Chrome version: $CHROME_VERSION"
else
  echo "Chrome binary not found at $CHROME_BIN"
  exit 1
fi

# Install ChromeDriver
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}")
echo "ChromeDriver version to install: $CHROMEDRIVER_VERSION"
wget -q -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip /tmp/chromedriver.zip -d $CHROME_DIR/opt/google/chrome/
chmod +x $CHROME_DIR/opt/google/chrome/chromedriver

# Verify ChromeDriver installation
if [[ -f $CHROME_DIR/opt/google/chrome/chromedriver ]]; then
  echo "ChromeDriver successfully installed"
else
  echo "Failed to install ChromeDriver"
  exit 1
fi

# Add Chrome and ChromeDriver to PATH
export PATH="$CHROME_DIR/opt/google/chrome:$PATH"

echo "Updated PATH: $PATH"

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
