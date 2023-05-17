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
            data = list()
        data.append(line)
    return data

STACK_NAME_INDEX = 1
STACK_ADDR_INDEX = 2
def stack_handle(line, priv):
    key_word = line.split()
    priv.append([key_word[STACK_NAME_INDEX], key_word[STACK_ADDR_INDEX]])

def null_init(line):
    return [line]

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
    "irq_handler_entry"                : ["irq",    null_init, null_handle, []],
    "irq_handler_exit"                 : ["irq",    null_init, null_handle, []],
    "softirq_entry"                    : ["irq",    null_init, null_handle, []],
    "softirq_exit"                     : ["irq",    null_init, null_handle, []],
    "softirq_raise"                    : ["irq",    null_init, null_handle, []],
    "<stack trace>"                    : ["ftrace", null_init, stack_handle, []],
    "<user stack trace>"               : ["ftrace", null_init, stack_handle, []]
}

def event_type_init():
    for mod_name, init_op, handle_op, event_type_list in event_type.values():
        event_type_list.clear()

TRACE_RETURN_TRUE=0
TRACE_RETURN_FALSE=1
TRACE_RETURN_STACK=2
"<...>-154717  ( 154717) [000] d.... 27117.357065: sched_stat_runtime: "
class trace_event:
    def __init__(self, line=""):
        self.available = TRACE_RETURN_TRUE
        if line.__len__() == 0:
            self.available = TRACE_RETURN_FALSE
            return
        if line[0] == '#':
            self.available = TRACE_RETURN_FALSE
            return
        if line[0:4] == ' => ':
            if len(line.split()) == 3:
                self.available = TRACE_RETURN_STACK
                return
            else:
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
            self.priv = init_op(line[end + 2 : -1])
        else:
            self.priv = list()
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