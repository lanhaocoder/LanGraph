#!/bin/bash
trace_path=`grep tracefs /proc/mounts |head -n 1|awk '{print $2}'`
if "$trace_path" = ""
then
trace_path="/sys/kernel/debug/tracing/"

