#!/bin/bash

docker run --rm --name openmotics_gateway -p 8443:443 -v $(pwd)/../../../frontend/dist:/opt/openmotics/static -it openmotics/gateway:latest
