#!/bin/sh
set -eu

# Map our R2 env vars onto the AWS standard names that boto3 reads.
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

# Substitute env vars into the giftless config template.
envsubst < /app/giftless.yaml.template > /app/giftless.yaml

exec "$@"
