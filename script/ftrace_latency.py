#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: lanhao
"""
import os
import time
import threading
import re
import pickle

INPUT_FILE_WITH_STACK="langraph.dat"
OUTPUT_FILE="langraph.out.txt"
TRACE_FILE="langraph.trace"

NAME_OFFSET=0
NAME_START=0
NAME_SIZE=16
NAME_END=NAME_START+NAME_SIZE
TID_OFFSET=1
TID_START=NAME_END+TID_OFFSET
TID_SIZE=7
TID_END=TID_START+TID_SIZE
PID_OFFSET=2
PID_START=TID_END+PID_OFFSET
PID_SIZE=7
PID_END=PID_START+PID_SIZE
CPU_OFFSET=3
CPU_START=PID_END+CPU_OFFSET
CPU_SIZE=3
CPU_END=CPU_START+CPU_SIZE
STATE_OFFSET=2
STATE_START=CPU_END+STATE_OFFSET
STATE_SIZE=5
STATE_END=STATE_START+STATE_SIZE

cpu_list={}
tid_list={}
pid_tid_list={}
irq_list={}
vec_list={}
cpu_stack_list={}
tid_stack_list={}

def save_variable(v,filename):
    f=open(filename,'wb')
    pickle.dump(v,f)
    f.close()
    return filename

def load_variavle(filename):
    f=open(filename,'rb')
    v=pickle.load(f)
    f.close()
    return v

def read_input(filename):
    f=open(filename,'r')
    lines = f.readlines()
    f.close()
    data=list()
    for line in lines:
        if "[LOST]" in line:
            del data
            print(line)
            data = list()
        data.append(line)
    return data

event_match={
    "sched_kthread_stop" : re.compile("comm=(\S+) pid=(\d+)"),
    "sched_kthread_stop_ret" : re.compile("ret=(\d+)"),
    "sched_kthread_work_execute_end" : re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
    "sched_kthread_work_execute_start" : re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
    "sched_kthread_work_queue_work" : re.compile("work struct=([-+]?(0[xX])?[\dA-Fa-f]+) function=(\S+) worker=([-+]?(0[xX])?[\dA-Fa-f]+)"),
    "sched_migrate_task" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) orig_cpu=(\d+) dest_cpu=(\d+)"),
    "sched_move_numa" : re.compile("pid=(\d+) tgid=(\d+) ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_pi_setprio" : re.compile("comm=(\S+) pid=(\d+) oldprio=(\d+) newprio=(\d+)"),
    "sched_process_exec" : re.compile("filename=(\S+) pid=(\d+) old_pid=(\d+)"),
    "sched_process_exit" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_process_fork" : re.compile("comm=(\S+) pid=(\d+) child_comm=(\S+) child_pid=(\d+)"),
    "sched_process_free" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_process_hang" : re.compile("comm=(\S+) pid=(\d+)"),
    "sched_process_wait" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_stat_blocked" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_iowait" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_runtime" : re.compile("comm=(\S+) pid=(\d+) runtime=(\d+) \[ns\] vruntime=(\d+) \[ns\]"),
    "sched_stat_sleep" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_wait" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stick_numa" : re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_swap_numa" : re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_switch" : re.compile("prev_comm=(\S+) prev_pid=(\d+) prev_prio=(\d+) prev_state=(\S+) ==> next_comm=(\S+) next_pid=(\d+) next_prio=(\d+)"),
    "sched_wait_task" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_wake_idle_without_ipi" : re.compile("cpu=(\d+)"),
    "sched_wakeup" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "sched_wakeup_new" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "sched_waking" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "irq_handler_entry" : re.compile("irq=(\d+) name=(\S+)"),
    "irq_handler_exit" : re.compile("irq=(\d+) ret=(\S+)"),
    "softirq_entry" : re.compile("vec=(\d+) \[action=(\S+)\]"),
    "softirq_exit" : re.compile("vec=(\d+) \[action=(\S+)\]"),
    "softirq_raise" : re.compile("vec=(\d+) \[action=(\S+)\]")
}

STACK_NAME_INDEX = 1
STACK_ADDR_INDEX = 2
def stack_handle(line, priv):
    key_word = line.split()
    priv.append([key_word[STACK_NAME_INDEX], key_word[STACK_ADDR_INDEX]])

def null_init(ev):
    return

def stack_init(ev):
    ev.priv = []
    return

def irq_init(ev):
    irq_info = ev.priv
    irq_num = irq_info[0]
    if irq_num not in irq_list:
        irq_ev_list = []
        irq_list[irq_num] = irq_ev_list
    else:
        irq_ev_list = irq_list[irq_num]
    irq_ev_list.append(ev)
    return

def softirq_init(ev):
    vec_info = ev.priv
    vec_num = vec_info[0]
    if vec_num not in vec_list:
        vec_ev_list = []
        vec_list[vec_num] = vec_ev_list
    else:
        vec_ev_list = vec_list[vec_num]
    vec_ev_list.append(ev)
    return

def null_handle(line, priv):
    return

mod_type = {
    "sched" : ["sched_kthread_stop",
        "sched_kthread_stop_ret",
        "sched_kthread_work_execute_end",
        "sched_kthread_work_execute_start",
        "sched_kthread_work_queue_work",
        "sched_migrate_task",
        "sched_move_numa",
        "sched_pi_setprio",
        "sched_process_exec",
        "sched_process_exit",
        "sched_process_fork",
        "sched_process_free",
        "sched_process_hang",
        "sched_process_wait",
        "sched_stat_blocked",
        "sched_stat_iowait",
        "sched_stat_runtime",
        "sched_stat_sleep",
        "sched_stat_wait",
        "sched_stick_numa",
        "sched_swap_numa",
        "sched_switch",
        "sched_wait_task",
        "sched_wake_idle_without_ipi",
        "sched_wakeup",
        "sched_wakeup_new",
        "sched_waking"],
	"irq" : ["irq_handler_entry",
        "irq_handler_exit",
        "softirq_entry",
        "softirq_exit",
        "softirq_raise"],
	"ftrace" : ["<stack trace>",
	    "<user stack trace>"]
}

event_type = {
    "sched_kthread_stop"               : ["sched",  null_init, null_handle, []],
    "sched_kthread_stop_ret"           : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_execute_end"   : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_execute_start" : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_queue_work"    : ["sched",  null_init, null_handle, []],
    "sched_migrate_task"               : ["sched",  null_init, null_handle, []],
    "sched_move_numa"                  : ["sched",  null_init, null_handle, []],
    "sched_pi_setprio"                 : ["sched",  null_init, null_handle, []],
    "sched_process_exec"               : ["sched",  null_init, null_handle, []],
    "sched_process_exit"               : ["sched",  null_init, null_handle, []],
    "sched_process_fork"               : ["sched",  null_init, null_handle, []],
    "sched_process_free"               : ["sched",  null_init, null_handle, []],
    "sched_process_hang"               : ["sched",  null_init, null_handle, []],
    "sched_process_wait"               : ["sched",  null_init, null_handle, []],
    "sched_stat_blocked"               : ["sched",  null_init, null_handle, []],
    "sched_stat_iowait"                : ["sched",  null_init, null_handle, []],
    "sched_stat_runtime"               : ["sched",  null_init, null_handle, []],
    "sched_stat_sleep"                 : ["sched",  null_init, null_handle, []],
    "sched_stat_wait"                  : ["sched",  null_init, null_handle, []],
    "sched_stick_numa"                 : ["sched",  null_init, null_handle, []],
    "sched_swap_numa"                  : ["sched",  null_init, null_handle, []],
    "sched_switch"                     : ["sched",  null_init, null_handle, []],
    "sched_wait_task"                  : ["sched",  null_init, null_handle, []],
    "sched_wake_idle_without_ipi"      : ["sched",  null_init, null_handle, []],
    "sched_wakeup"                     : ["sched",  null_init, null_handle, []],
    "sched_wakeup_new"                 : ["sched",  null_init, null_handle, []],
    "sched_waking"                     : ["sched",  null_init, null_handle, []],
    "irq_handler_entry"                : ["irq",    irq_init, null_handle, []],
    "irq_handler_exit"                 : ["irq",    irq_init, null_handle, []],
    "softirq_entry"                    : ["irq",    softirq_init, null_handle, []],
    "softirq_exit"                     : ["irq",    softirq_init, null_handle, []],
    "softirq_raise"                    : ["irq",    softirq_init, null_handle, []],
    "<stack trace>"                    : ["ftrace", stack_init, stack_handle, []],
    "<user stack trace>"               : ["ftrace", stack_init, stack_handle, []]
}

def event_type_init():
    for mod_name, init_op, handle_op, event_type_list in event_type.values():
        event_type_list.clear()

def event_type_print_priv():
    for name in event_type:
        [mod_name, init, handle, ev] = event_type[name]
        if len(ev) != 0:
            print(name, ev[0].priv)
        else:
            print(name)

TRACE_RETURN_TRUE=0
TRACE_RETURN_FALSE=1
TRACE_RETURN_STACK=2
"<...>-154717  ( 154717) [000] d.... 27117.357065: sched_stat_runtime: "
class trace_event:
    def init_common(self):
        if self.cpu not in cpu_list:
            cpu_ev_list = []
            cpu_list[self.cpu] = cpu_ev_list
        else:
            cpu_ev_list = cpu_list[self.cpu]
        cpu_ev_list.append(self)
        if self.tid not in tid_list:
            tid_ev_list = []
            tid_list[self.tid] = tid_ev_list
        else:
            tid_ev_list = tid_list[self.tid]
        tid_ev_list.append(self)
        if self.pid not in pid_tid_list:
            pid_ev_list = set()
            pid_tid_list[self.pid] = pid_ev_list
        else:
            pid_ev_list = pid_tid_list[self.pid]
        pid_ev_list.add(self.tid)
        return
    def __init__(self, line=""):
        self.available = TRACE_RETURN_TRUE
        if line[0:4] == ' => ':
            if len(line.split()) == 3:
                self.available = TRACE_RETURN_STACK
                return
            else:
                self.available = TRACE_RETURN_FALSE
                return
        elif line.__len__() == 0:
            self.available = TRACE_RETURN_FALSE
            return
        elif line[0] == '#':
            self.available = TRACE_RETURN_FALSE
            return
        self.name  = line[ NAME_START: NAME_END].strip()
        self.tid   = line[  TID_START:  TID_END].strip()
        self.pid   = line[  PID_START:  PID_END].strip()
        self.cpu   = int(line[  CPU_START:  CPU_END].strip())
        self.state = line[STATE_START:STATE_END].strip()
        key_word = line[TID_START:-1].split(':')
        self.timestamp = float(key_word[0].split()[-1])
        self.event_name = key_word[1].strip()
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            (start, end) = re.search(self.event_name, line).span()
            event_type_list.append(self)
            info = line[end + 2 : -1]
            if self.event_name not in event_match:
                self.priv = info
                init_op(self)
                self.init_common()
                return
            pattern = event_match[self.event_name]
            match = pattern.match(info)
            if match is not None:
                self.priv = match.groups()
                init_op(self)
            else:
                self.priv = info
                init_op(self)
        else:
            self.priv = line
        self.init_common()

    def get_available(self):
        return self.available
    def handle(self, line):
        if self.available != TRACE_RETURN_TRUE:
            return
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            handle_op(line, self.priv)

def parse_data(data):
    data_len = len(data)
    event_type_init()
    if data_len == 0:
        return
    last_te = trace_event(data[0])
    te_list=list()
    for i in range(0, data_len):
        line = data[i]
        #print(line)
        te = trace_event(line)
        if te.get_available() == TRACE_RETURN_FALSE:
            continue
        if te.get_available() == TRACE_RETURN_STACK:
            if last_te.get_available() == TRACE_RETURN_TRUE:
                last_te.handle(line)
                continue
            continue
        last_te = te
        te_list.append(te)
    return te_list

if __name__ == '__main__':
    data = read_input(INPUT_FILE_WITH_STACK)
    te_list=parse_data(data)