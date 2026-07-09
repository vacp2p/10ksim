#!/bin/sh

logoscore daemon --modules-dir "$HOME/.logos/modules" --module-transport core_service=tcp,host=0.0.0.0,port=8645 --module-transport capability_module=tcp,host=0.0.0.0,port=8646 --insecure-tcp &


# Wait until logoscore is running by checking the port.
while ! nc -z localhost 8645; do
  sleep 0.1
done

logoscore load-module delivery_module
logoscore load-module openmetrics
logoscore status
logoscore issue-token --name $HOSTNAME

python3 ./main.py

wait