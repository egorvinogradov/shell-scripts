#!/bin/bash

k="com.apple.speech.recognition.AppleSpeechRecognition.prefs DictationIMLocaleIdentifier"
if [[ "$(defaults read $k)" == en-US ]]; then
  defaults write $k ru-RU
  defaults write com.apple.assistant "Session Language" ru-RU
else
  defaults write $k en-US 
  defaults write com.apple.assistant "Session Language" en-US
fi
killall -HUP DictationIM || echo nope
