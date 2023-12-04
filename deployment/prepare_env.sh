#!/bin/bash

ulimit -n $(ulimit -n -H)
ulimit -u $(ulimit -u -H)

sudo sysctl -w net.ipv4.neigh.default.gc_thresh1=65536
sudo sysctl -w net.ipv4.neigh.default.gc_thresh2=114688
sudo sysctl -w net.ipv4.neigh.default.gc_thresh3=131072
sudo sysctl fs.inotify.max_user_instances=1048576
sudo sysctl -w vm.max_map_count=262144

echo 11000 > /proc/sys/kernel/pty/max
