[app]
title = AynIQ Shooter
package.name = ayniq
package.domain = com.jefo
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,onnx,ttf
version = 1.0.0
requirements = python3,kivy,requests,urllib3,numpy==1.26.4,pillow,arabic_reshaper,python-bidi,opencv
orientation = portrait
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.skip_update = False
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
