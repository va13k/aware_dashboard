#!/bin/sh
printf "Content-Type: application/json\r\n\r\n"

if [ -f /tmp/deploy.done ]; then
    RC=$(cat /tmp/deploy.done)
    if [ "$RC" = "0" ]; then
        printf '{"status":"done","success":true}'
    else
        ERROR=$(cat /tmp/compose.log 2>/dev/null | tr '"' "'" | tr '\n' ' ' | head -c 500)
        printf '{"status":"done","success":false,"error":"%s"}' "$ERROR"
    fi
elif [ -f /tmp/deploy.running ]; then
    LINE=$(tail -1 /tmp/compose.log 2>/dev/null | tr '"' "'" | tr '\n' ' ' | head -c 200)
    printf '{"status":"running","log":"%s"}' "$LINE"
else
    printf '{"status":"idle"}'
fi