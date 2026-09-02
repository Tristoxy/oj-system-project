#!/usr/bin/env sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

docker build \
  --tag oj-python:3.10 \
  --file "$project_dir/docker/judge-python.Dockerfile" \
  "$project_dir"
docker build \
  --tag oj-cpp:gcc13 \
  --file "$project_dir/docker/judge-cpp.Dockerfile" \
  "$project_dir"
