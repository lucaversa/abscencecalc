#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Starting build process"

STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "Downloading Chrome"
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -P ./ https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm ./google-chrome-stable_current_amd64.deb
  echo "Chrome downloaded and extracted"
else
  echo "Using Chrome from cache"
fi

echo "Returning to project directory"
cd $HOME/project/src

echo "Installing Python dependencies"
pip install -r requirements.txt

echo "Build process completed"
