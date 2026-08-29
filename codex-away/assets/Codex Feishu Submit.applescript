tell application id "com.openai.codex" to activate

tell application "System Events"
    repeat 100 times
        if exists application process "ChatGPT" then
            if frontmost of application process "ChatGPT" then exit repeat
        end if
        delay 0.1
    end repeat

    if not (exists application process "ChatGPT") then
        error "Codex process is unavailable"
    end if
    if not frontmost of application process "ChatGPT" then
        error "Codex did not become frontmost"
    end if

    delay 1
    key code 36
end tell
