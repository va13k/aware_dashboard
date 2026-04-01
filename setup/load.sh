#!/bin/sh

printf "Content-Type: application/json\r\n\r\n"

if [ -f /project/.env ]; then
    ENV_CONTENT=$(cat /project/.env | tr '\n' '\\' | sed 's/\\/\\n/g' | sed 's/\\n$//')
    printf '{"env":"%s"}' "$ENV_CONTENT"
else
    printf '{"env":null}'
fi