#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: Hao Lan
"""
import os
import sys
import argparse
"""
" trace-cmd record -e sched -e irq -C perf -m 65536 -s 1000000 -b 65536 -T "
"""
def read_file(filename=""):
    with open(filename, encoding='utf-8') as fd:
        lines = fd.readlines()
        fd.close()
        return lines
    return ""

def get_tracefs_path():
    lines = read_file("/proc/mounts")
    for line in lines:
        if "tracefs" in line:
            return line.split()[1]
    return ""

def main():
    parser = argparse.ArgumentParser(description='manual to this script')
    parser.add_argument("--time", "-t", type=int, default=10)
    parser.add_argument("--output", "-o", type=str, default="langraph.dat")
    parser.add_argument("--max_buffer_size_kb", "-m", type=int, default=65536)
    flag_parser = parser.add_mutually_exclusive_group(required=False)
    flag_parser.add_argument('-T', dest='stacktrace', action='store_true')
    parser.set_defaults(stacktrace=False)
    parser.add_argument('--event', "-e", type=str, action='extend', nargs='+', default=["sched","irq"])
    parser.add_argument('--clock', "-C", type=str, default="perf")
    parser.add_argument('--interval', "-s", type=int, default=1000000)
    parser.add_argument('--buffer_size_kb', "-b", type=int, default=65536)
    args = parser.parse_args()
    print(args.time)
    print(args.output)
    print(args.buffer_size_kb)
    print(args.stacktrace)
    print(set(args.event))
    print(args.stacktrace)

if __name__ == '__main__':
    main()

