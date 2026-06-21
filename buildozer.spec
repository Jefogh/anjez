name: Build Kivy APK

on:
  push:
    branches: [ main ]
  workflow_dispatch: # هذا السطر يسمح لك بتشغيل التجميع يدوياً بضغطة زر

jobs:
  build:
    runs-on: ubuntu-22.04

    steps:
    - name: Checkout repository
      uses: actions/checkout@v3

    - name: Install Dependencies
      run: |
        sudo apt update
        sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
        pip3 install --user --upgrade buildozer cython virtualenv

    - name: Run Buildozer
      run: |
        export PATH=$PATH:~/.local/bin
        # تأكيد الموافقة على رخص الأندرويد وبدء التجميع
        yes | buildozer android debug

    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: AynIQ-App-APK
        path: bin/*.apk
