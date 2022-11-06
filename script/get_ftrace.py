#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: Hao Lan
"""
import os
import sys
import argparse
import time
import shutil
import signal
import gzip

"""
" trace-cmd record -e sched -e irq -C perf -m 65536 -s 1000000 -b 65536 -T "
"""
tracefs_dir_global=""

def read_file(filename=""):
    with open(filename, 'r') as fd:
        lines = fd.readlines()
        fd.close()
        return lines
    return ""

def write_file(filename="", data=""):
    print(filename, data)
    with open(filename, 'w') as fd:
        fd.write(data)
        fd.close()

class ftrace_capture:
    def get_tracefs_path(self):
        global tracefs_dir_global
        lines = read_file("/proc/mounts")
        for line in lines:
            if "tracefs" in line:
                tracefs_dir_global = line.split()[1]+"/"
                return line.split()[1]+"/"
        return ""
    def __init__(self, opt):
        self.time = opt.time
        self.output = opt.output
        self.buffer_size_kb = opt.buffer_size_kb
        self.stacktrace = opt.stacktrace
        self.events = set(opt.events)
        self.clock = opt.clock
        self.notgid = opt.notgid
        self.tracefs_path = self.get_tracefs_path()
        self.gzip = opt.gzip

    def set_option(self, opt):
        self.time = opt.time
        self.output = opt.output
        self.buffer_size_kb = opt.buffer_size_kb
        self.stacktrace = opt.stacktrace
        self.events = set(opt.events)
        self.clock = opt.clock
        self.notgid = opt.notgid
        self.tracefs_path = self.get_tracefs_path()
        self.gzip = opt.gzip

    def perpare(self):
        def_ftrace_opt="""
            annotate           1
            bin                0
            blk_cgname         0
            blk_cgroup         0
            blk_classic        0
            block              0
            context-info       1
            disable_on_free    0
            display-graph      0
            event-fork         0
            funcgraph-abstime  0
            funcgraph-cpu      1
            funcgraph-duration 1
            funcgraph-irqs     1
            funcgraph-overhead 1
            funcgraph-overrun  0
            funcgraph-proc     0
            funcgraph-tail     0
            func-no-repeats    0
            func_stack_trace   0
            function-fork      0
            function-trace     1
            graph-time         1
            hash-ptr           1
            hex                0
            irq-info           1
            latency-format     0
            markers            1
            overwrite          1
            pause-on-trace     0
            printk-msg-only    0
            print-parent       1
            raw                0
            record-cmd         1
            record-tgid        0
            sleep-time         1
            stacktrace         0
            sym-addr           0
            sym-offset         0
            sym-userobj        0
            test_nop_accept    0
            test_nop_refuse    0
            trace_printk       1
            userstacktrace     0
            verbose            0
            """
        def_ftrace="""
            buffer_size_kb      65536
            current_tracer      nop
            saved_cmdlines_size 128 
            trace_clock         perf
            tracing_on          0
            trace
            """
        write_file("/proc/sys/kernel/ftrace_enabled", "1")
        write_file("/proc/sys/kernel/kptr_restrict", "1")
        for line in def_ftrace_opt.split('\n'):
            word = line.split()
            if len (word) == 0:
                continue
            if len(word) >= 2:
                write_file(self.tracefs_path+"options/"+word[0], word[1])
            else:
                write_file(self.tracefs_path+"options/"+word[0], "")
        for line in def_ftrace.split('\n'):
            word = line.split()
            if len (word) == 0:
                continue
            if len(word) >= 2:
                write_file(self.tracefs_path+word[0], word[1])
            else:
                write_file(self.tracefs_path+word[0], "")
        write_file(self.tracefs_path+"buffer_size_kb", self.buffer_size_kb)
        write_file(self.tracefs_path+"trace_clock", self.clock)
        if self.notgid is False:
            write_file(self.tracefs_path+"options/"+"record-tgid", "1")
        else:
            write_file(self.tracefs_path+"options/"+"record-tgid", "0")
        if self.stacktrace is True:
            write_file(self.tracefs_path+"options/"+"sym-addr", "1")
            write_file(self.tracefs_path+"options/"+"sym-offset", "1")
            write_file(self.tracefs_path+"options/"+"sym-userobj", "1")
            write_file(self.tracefs_path+"options/"+"userstacktrace", "1")
            write_file(self.tracefs_path+"options/"+"stacktrace", "1")
        else:
            write_file(self.tracefs_path+"options/"+"sym-addr", "0")
            write_file(self.tracefs_path+"options/"+"sym-offset", "0")
            write_file(self.tracefs_path+"options/"+"sym-userobj", "0")
            write_file(self.tracefs_path+"options/"+"userstacktrace", "0")
            write_file(self.tracefs_path+"options/"+"stacktrace", "0")
        for e in self.events:
            e.replace(":","/")
            write_file(self.tracefs_path+"events/"+e+"/enable", "1")
        write_file(self.tracefs_path+"tracing_on", "0")
        write_file(self.tracefs_path+"trace", "")
        
    def start(self):
        print("Capture for "+str(self.time)+" seconds start.")
        print("Enter Ctrl+C to stop capture...")
        write_file(self.tracefs_path+"tracing_on", "1")
        time.sleep(self.time)

    def save(self):
        write_file(self.tracefs_path+"tracing_on", "0")
        if self.gzip is False:
            shutil.copyfile(self.tracefs_path+"trace", self.output)
        else:
            g = gzip.GzipFile(filename=self.output, mode="w", compresslevel=9, fileobj=open(self.output+'.gz', 'wb'))
            g.write(open(self.tracefs_path+"trace", 'rb').read())
            g.close()

def main():
    parser = argparse.ArgumentParser(description='manual to this script')
    parser.add_argument("--time", "-t", type=int, default=60)
    parser.add_argument("--output", "-o", type=str, default="langraph.dat")
    parser.add_argument("--max_buffer_size_kb", "-m", type=str, default='65536')
    parser.add_argument('-T', dest='stacktrace', action='store_true')
    parser.set_defaults(stacktrace=False)
    parser.add_argument('--notgid', action='store_true')
    parser.set_defaults(notgid=False)
    parser.add_argument('--record', action='store_true')
    parser.set_defaults(record=False)
    parser.add_argument('-z', dest='gzip', action='store_true')
    parser.set_defaults(gzip=False)
    parser.add_argument('--events', "-e", type=str, action='extend', nargs='+', default=["sched","irq"])
    parser.add_argument('--clock', "-C", type=str, default="perf")
    parser.add_argument('--interval', "-s", type=int, default=1000000)
    parser.add_argument('--buffer_size_kb', "-b", type=str, default='65536')
    args = parser.parse_args()
    cap = ftrace_capture(args)
    if args.record == False:
        cap.perpare()
        cap.start()
    cap.save()

def exit_capture(signum, frame):
    global tracefs_dir_global
    write_file(tracefs_dir_global+"tracing_on", "0")
    print("Stop capture.")
    exit()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, exit_capture)
    signal.signal(signal.SIGTERM, exit_capture)
    main()
